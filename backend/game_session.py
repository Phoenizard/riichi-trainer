"""
Game session — manages engine thread lifecycle and AI agents.

One GameSession per active game. Engine runs in a separate thread.
WebAgent bridges the async WS handler to the sync engine.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from game.engine import GameEngine, RoundState
from ai.mock_agent import MockAgent
from backend.db import GameLogger
from backend.web_agent import WebAgent, GameInterrupted, serialize_game_info, serialize_meld

logger = logging.getLogger(__name__)

MODEL_PATH = "model/model_v4_20240308_best_min.pth"


def _mortal_available() -> bool:
    """Check if Mortal (libriichi + model) is available."""
    try:
        if not os.path.exists(MODEL_PATH):
            return False
        from ai.mortal_agent import MortalAgent  # noqa: F401
        import libriichi  # noqa: F401
        return True
    except ImportError:
        return False


class GameSession:
    """Manages a single game: WebAgent + AI opponents + engine thread."""

    def __init__(self, use_mortal: Optional[bool] = None):
        self.web_agent = WebAgent()
        self._round_continue = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.engine: Optional[GameEngine] = None
        self._running = False
        self.logger = GameLogger()
        self.game_id: Optional[str] = None
        self.round_index = 0
        self._current_round_id: Optional[str] = None

        # Auto-detect Mortal if not specified
        if use_mortal is None:
            use_mortal = _mortal_available()

        self.use_mortal = use_mortal

        # Create AI opponents
        if use_mortal:
            from ai.mortal_agent import MortalAgent
            self.ai_agents = [
                MortalAgent.create_libriichi(i, MODEL_PATH) for i in range(1, 4)
            ]
            # Coach: shadow MortalAgent at seat 0
            self.web_agent._coach = MortalAgent.create_libriichi(0, MODEL_PATH)
            logger.info("Using Mortal AI (local libriichi)")
        else:
            self.ai_agents = [MockAgent(f"AI-{i}") for i in range(1, 4)]
            logger.info("Using MockAgent (heuristic fallback)")

    def start(self) -> None:
        """Start the game in a background thread."""
        agents = [self.web_agent] + self.ai_agents
        self.engine = GameEngine(agents)
        self.web_agent._engine_ref = self.engine
        self.web_agent._logger = self.logger
        self.engine.round_callback = self._on_round_end
        self.game_id = self.logger.start_game()
        self.round_index = 0
        # Create first round record so decisions can reference it
        first_round_id = self.logger.start_round(self.game_id, 0)
        self.web_agent._current_round_id = first_round_id
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Engine thread entry point."""
        try:
            scores = self.engine.play_game()
            self.web_agent.ws_send_queue.put({
                "type": "game_over",
                "scores": scores,
            })
            # Finalize game record
            if self.game_id:
                placement = sorted(range(4), key=lambda i: scores[i], reverse=True).index(0) + 1
                self.logger.end_game(self.game_id, list(scores), placement)
        except GameInterrupted:
            logger.info("Game interrupted")
            if self.game_id and self.engine:
                self.logger.end_game(self.game_id, list(self.engine.game_scores), 0)
        except Exception as e:
            logger.exception(f"Engine error: {e}")
            self.web_agent.ws_send_queue.put({
                "type": "error",
                "message": str(e),
            })
        finally:
            self._running = False

    def _on_round_end(self, state: RoundState) -> None:
        """Called by engine after each round (in engine thread)."""
        # Finalize round in database and prepare next
        round_stats = None
        if self.game_id:
            current_round_id = self.web_agent._current_round_id
            self.logger.end_round(current_round_id, state)
            round_stats = self.logger.get_round_stats(current_round_id)
            self.round_index += 1
            # Pre-create next round record for upcoming decisions
            next_round_id = self.logger.start_round(self.game_id, self.round_index)
            self.web_agent._current_round_id = next_round_id

        # Build winner's hand data
        winning_hand = []
        winning_melds = []
        if state.winner >= 0:
            wp = state.players[state.winner]
            winning_hand = wp.hand + ([wp.draw_tile] if wp.draw_tile else [])
            winning_melds = [serialize_meld(m) for m in wp.melds]

        # Build tenpai hands for draw results
        tenpai_hands = {}
        for seat, data in state.tenpai_hands.items():
            tenpai_hands[seat] = {
                "hand": data["hand"],
                "melds": [serialize_meld(m) for m in data["melds"]],
            }

        # Send round result
        msg = {
            "type": "round_result",
            "result": state.result.value if state.result else "unknown",
            "winner": state.winner,
            "loser": state.loser,
            "han": state.han,
            "fu": state.fu,
            "yaku": state.yaku,
            "score_deltas": state.score_deltas,
            "scores": list(self.engine.game_scores),
            "winning_hand": winning_hand,
            "winning_melds": winning_melds,
            "tenpai_hands": tenpai_hands,
        }
        if round_stats:
            msg["round_stats"] = round_stats
        self.web_agent.ws_send_queue.put(msg)

        # Block until frontend sends "continue_round"
        # Same pattern as terminal UI's input("Enter で続行...")
        self._round_continue.clear()
        self._round_continue.wait(timeout=120)

    def continue_round(self) -> None:
        """Unblock the engine thread after round result is acknowledged."""
        self._round_continue.set()

    def stop(self) -> None:
        """Stop the game session gracefully."""
        self._running = False
        # Unblock all waiting events
        self.web_agent._shutdown.set()
        self.web_agent._action_event.set()
        self._round_continue.set()
        # Sentinel to exit send_loop
        self.web_agent.ws_send_queue.put(None)
        # Wait for engine thread
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    @property
    def is_running(self) -> bool:
        return self._running

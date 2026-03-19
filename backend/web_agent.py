"""
WebAgent — bridges async WebSocket ↔ sync GameEngine.

Implements the Agent protocol (choose_action + on_event).
Engine thread blocks on threading.Event; WebSocket handler signals it.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

from game.engine import Action, ActionType, RoundState
from game.tiles import sort_tiles

logger = logging.getLogger(__name__)


class GameInterrupted(Exception):
    """Raised when the game is interrupted (disconnect / shutdown)."""
    pass


class WebAgent:
    """Bridges async WebSocket ↔ sync GameEngine via threading primitives."""

    def __init__(self, ai_delay: float = 1.2):
        self._action_event = threading.Event()
        self._chosen_action: Optional[Action] = None
        self._pending_actions: Optional[list[Action]] = None
        self._shutdown = threading.Event()
        self._coach = None  # Optional MortalAgent for coaching
        self._engine_ref = None  # Set by GameSession after engine creation
        self.ws_send_queue: queue.Queue = queue.Queue()
        self.ai_delay = ai_delay  # seconds to pause between AI actions

    def choose_action(
        self,
        player_id: int,
        game_state: RoundState,
        available_actions: list[Action],
    ) -> Action:
        """Called by GameEngine in engine thread. Blocks until player responds."""
        # Send current game state so frontend can render the table
        self.ws_send_queue.put(serialize_game_info(game_state, self._engine_ref))

        # Coach analysis — already computed by on_event(), just read it
        if self._coach:
            try:
                analysis = self._coach.get_analysis()
                if analysis:
                    self.ws_send_queue.put({
                        "type": "coach",
                        "analysis": {
                            "recommended": analysis.recommended_tile,
                            "recommended_action": analysis.recommended_action,
                            "shanten": analysis.shanten,
                            "candidates": analysis.candidates[:10],
                        }
                    })
            except Exception as e:
                logger.warning(f"Coach analysis error: {e}")

        # Send action_required to frontend
        ps = game_state.players[player_id]
        self.ws_send_queue.put({
            "type": "action_required",
            "available_actions": serialize_actions(available_actions),
            "hand": sort_tiles(ps.hand),
            "draw_tile": ps.draw_tile,
        })

        # Block until player responds via WebSocket
        self._pending_actions = available_actions
        self._action_event.clear()
        self._action_event.wait(timeout=300)

        if self._shutdown.is_set():
            raise GameInterrupted("Game interrupted by shutdown")

        if self._chosen_action is None:
            raise GameInterrupted("No action received (timeout)")

        return self._chosen_action

    def receive_player_action(self, action_data: dict) -> None:
        """Called from WS handler when client sends an action."""
        if self._pending_actions is None:
            logger.warning("Received action but no pending actions")
            return

        self._chosen_action = parse_ws_action(action_data, self._pending_actions)
        self._action_event.set()

    def on_event(self, event: dict) -> None:
        """Receive game event from engine — forward to WS and coach."""
        # Pause on AI player actions so human can follow the game
        etype = event.get("type")
        player = event.get("player")
        if player is not None and player != 0 and etype in (
            "discard", "pon", "chi", "kan", "riichi", "reach", "reach_accepted",
            "tsumo", "ron",
        ):
            time.sleep(self.ai_delay)

        self.ws_send_queue.put({"type": "game_event", "event": event})
        if self._coach:
            try:
                self._coach.on_event(event)
            except Exception as e:
                logger.warning(f"Coach on_event error: {e}")


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def serialize_actions(actions: list[Action]) -> list[dict]:
    """Serialize engine Action objects to JSON-friendly dicts."""
    result = []
    for a in actions:
        d: dict = {"type": a.type.value}
        if a.tile:
            d["tile"] = a.tile
        if a.meld_tiles:
            d["meld_tiles"] = a.meld_tiles
        result.append(d)
    return result


def serialize_meld(meld) -> dict:
    """Serialize a Meld object."""
    return {
        "type": meld.type.value,
        "tiles": meld.tiles,
        "from_player": meld.from_player,
        "called_tile": meld.called_tile,
    }


WIND_KANJI = {0: "東", 1: "南", 2: "西", 3: "北"}
WIND_FROM_STR = {"E": "東", "S": "南", "W": "西", "N": "北"}


def serialize_player(ps, seat: int, dealer: int, is_self: bool = False) -> dict:
    """Serialize PlayerState for WS, applying visibility rules."""
    seat_wind_idx = (seat - dealer) % 4
    d = {
        "discards": ps.discards,
        "melds": [serialize_meld(m) for m in ps.melds],
        "is_riichi": ps.is_riichi,
        "riichi_turn": ps.riichi_turn,
        "hand_count": len(ps.hand) + (1 if ps.draw_tile else 0),
        "seat_wind": WIND_KANJI.get(seat_wind_idx, ""),
    }
    # Always include hand (single-player trainer, no security concern)
    d["hand"] = sort_tiles(ps.hand)
    d["draw_tile"] = ps.draw_tile
    return d


def serialize_game_info(state: RoundState, engine=None) -> dict:
    """Serialize round/game info for the game_info WS message."""
    scores = list(engine.game_scores) if engine else list(state.scores)
    return {
        "type": "game_info",
        "round_wind": WIND_FROM_STR.get(state.round_wind, state.round_wind),
        "round_number": state.round_number,
        "honba": state.honba,
        "riichi_sticks": state.riichi_sticks,
        "scores": scores,
        "dora_indicators": state.dora_indicators,
        "tiles_remaining": state.tiles_remaining,
        "dealer": state.dealer,
        "current_turn": state.current_turn,
        "players": [
            serialize_player(state.players[i], i, state.dealer, is_self=(i == 0))
            for i in range(4)
        ],
    }


def parse_ws_action(action_data: dict, available_actions: list[Action]) -> Action:
    """Parse a WS action message and match to an available engine Action."""
    action_type = action_data.get("action_type", "")
    tile = action_data.get("tile", "")
    meld_tiles = action_data.get("meld_tiles", [])

    # Try exact match first
    for a in available_actions:
        if a.type.value != action_type:
            continue
        # For discard/riichi: match tile
        if action_type in ("discard", "riichi"):
            if a.tile == tile:
                return a
        # For chi: match meld_tiles
        elif action_type == "chi":
            if sorted(a.meld_tiles) == sorted(meld_tiles) and a.tile == tile:
                return a
        # For pon/kan: match tile
        elif action_type in ("pon", "kan"):
            if a.tile == tile:
                return a
        # For tsumo/ron/skip: no tile needed
        elif action_type in ("tsumo", "ron", "skip", "kyuushu"):
            return a

    # Fallback: find any action of the same type
    for a in available_actions:
        if a.type.value == action_type:
            return a

    # Last resort: first available
    logger.warning(f"Could not match action {action_data}, using first available")
    return available_actions[0]

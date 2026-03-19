"""
WebAgent — bridges async WebSocket I/O to the synchronous GameEngine.

The GameEngine calls choose_action() on its thread; WebAgent blocks that
thread until the frontend sends a response via the WebSocket handler.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

from game.engine import RoundState, Action, ActionType, MeldType, GameEngine
from game.tiles import sort_tiles
from game.efficiency import calculate_efficiency, calculate_shanten

logger = logging.getLogger(__name__)


class GameInterrupted(Exception):
    """Raised when game is interrupted (e.g., client disconnect)."""
    pass


class WebAgent:
    """Agent that bridges WebSocket I/O to the synchronous engine thread."""

    def __init__(self, engine: Optional[GameEngine] = None,
                 coach=None, ai_delay: float = 0.8):
        self._engine_ref = engine
        self._coach = coach
        self._pending_actions: Optional[list[Action]] = None
        self._chosen_action: Optional[Action] = None
        self._action_event = threading.Event()
        self._shutdown = threading.Event()
        self._logger = None
        self._current_round_id: Optional[str] = None
        self._turn_number: int = 0
        self._last_coach_analysis = None  # Cache for logging
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

        ps = game_state.players[player_id]

        # Riichi auto-discard: only tsumogiri available — show draw tile briefly, then auto-respond
        if len(available_actions) == 1 and available_actions[0].type == ActionType.DISCARD:
            msg: dict = {
                "type": "action_required",
                "available_actions": [],
                "hand": sort_tiles(ps.hand),
                "draw_tile": ps.draw_tile,
            }
            self.ws_send_queue.put(msg)
            time.sleep(max(self.ai_delay, 1.0))
            self._chosen_action = available_actions[0]
            return self._chosen_action

        # Coach analysis — already computed by on_event(), just read it
        self._last_coach_analysis = None
        if self._coach:
            try:
                analysis = self._coach.get_analysis()
                if analysis:
                    self._last_coach_analysis = analysis
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

        # If tsumo is available, add a skip option so player can decline
        has_tsumo = any(a.type == ActionType.TSUMO for a in available_actions)
        if has_tsumo and not any(a.type == ActionType.SKIP for a in available_actions):
            available_actions = list(available_actions) + [Action(ActionType.SKIP, player_id)]

        # Compute tile efficiency (only when player has discard actions)
        efficiency_data = None
        has_discard = any(a.type == ActionType.DISCARD for a in available_actions)
        if has_discard:
            visible: list[str] = []
            for p in game_state.players:
                visible.extend(p.discards)
                for m in p.melds:
                    visible.extend(m.tiles)
                visible.extend(game_state.dora_indicators)

            full_hand = list(ps.hand) + ([ps.draw_tile] if ps.draw_tile else [])
            rows = calculate_efficiency(full_hand, visible)
            efficiency_data = [
                {
                    "discard": r.discard,
                    "accepts": r.accepts,
                    "total": r.total,
                    "remaining": r.remaining,
                }
                for r in rows
            ]

        # Send action_required to frontend
        msg = {
            "type": "action_required",
            "available_actions": serialize_actions(available_actions),
            "hand": sort_tiles(ps.hand),
            "draw_tile": ps.draw_tile,
        }
        if efficiency_data is not None:
            full_hand = list(ps.hand) + ([ps.draw_tile] if ps.draw_tile else [])
            msg["efficiency"] = efficiency_data
            msg["shanten"] = calculate_shanten(full_hand[:-1]) if len(full_hand) >= 14 else None
        self.ws_send_queue.put(msg)

        # Block until player responds via WebSocket
        self._pending_actions = available_actions
        self._action_event.clear()
        self._action_event.wait(timeout=300)

        if self._shutdown.is_set():
            raise GameInterrupted("Game interrupted by shutdown")

        if self._chosen_action is None:
            raise GameInterrupted("No action received (timeout)")

        # Log decision to database
        if self._logger and self._current_round_id:
            try:
                chosen = self._chosen_action
                coach = self._last_coach_analysis
                # Determine what AI recommended
                ai_rec = coach.recommended_tile if coach else None
                ai_action = coach.recommended_action if coach else None
                shanten = coach.shanten if coach else None
                # Determine match
                is_match = False
                if coach:
                    if ai_action == "dahai" and chosen.type == ActionType.DISCARD:
                        is_match = chosen.tile == ai_rec
                    elif ai_action == "none" and chosen.type.value == "skip":
                        is_match = True
                    elif ai_action in ("pon", "chi", "hora", "reach") and chosen.type.value == ai_action:
                        is_match = True

                self._logger.log_decision(
                    round_id=self._current_round_id,
                    turn_number=self._turn_number,
                    action_type=chosen.type.value,
                    player_action=chosen.tile or chosen.type.value,
                    ai_recommendation=ai_rec or (ai_action if ai_action else None),
                    ai_action_type=ai_action,
                    match=is_match,
                    shanten=shanten,
                    hand=sort_tiles(ps.hand),
                )
                self._turn_number += 1
            except Exception as e:
                logger.warning(f"Decision logging error: {e}")

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
        etype = event.get("type")

        # Reset turn counter on new round
        if etype == "start_round":
            self._turn_number = 0

        # Pause on AI player actions so human can follow the game
        player = event.get("player")
        if player is not None and player != 0 and etype in (
            "discard", "pon", "chi", "kan", "riichi", "reach", "reach_accepted",
            "tsumo", "ron",
        ):
            import time
            time.sleep(self.ai_delay)

        # Forward to frontend
        self.ws_send_queue.put({"type": "game_event", "event": event})

        # Feed event to coach for next analysis
        if self._coach:
            try:
                self._coach.on_event(event)
            except Exception as e:
                logger.warning(f"Coach event error: {e}")

    def shutdown(self):
        self._shutdown.set()
        self._action_event.set()


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def serialize_meld(m) -> dict:
    return {
        "type": m.type.value,
        "tiles": m.tiles,
        "from_player": m.from_player,
        "called_tile": m.called_tile,
    }


def serialize_actions(actions: list[Action]) -> list[dict]:
    result = []
    for a in actions:
        d: dict = {"type": a.type.value}
        if a.tile:
            d["tile"] = a.tile
        if a.meld_tiles:
            d["meld_tiles"] = a.meld_tiles
        result.append(d)
    return result


def serialize_game_info(state: RoundState, engine: Optional[GameEngine]) -> dict:
    """Build game_info message from current RoundState."""
    d: dict = {
        "type": "game_info",
        "round_wind": state.round_wind,
        "round_number": state.round_number,
        "honba": state.honba,
        "riichi_sticks": engine.riichi_sticks if engine else 0,
        "scores": list(engine.game_scores) if engine else [25000] * 4,
        "dora_indicators": state.dora_indicators,
        "tiles_remaining": state.tiles_remaining,
        "dealer": state.dealer,
        "current_turn": state.current_turn,
        "players": [],
    }
    seat_winds = ["E", "S", "W", "N"]
    for i, ps in enumerate(state.players):
        wind_offset = (i - state.dealer) % 4
        p: dict = {
            "discards": ps.discards,
            "melds": [serialize_meld(m) for m in ps.melds],
            "is_riichi": ps.is_riichi,
            "riichi_turn": ps.riichi_turn,
            "hand_count": len(ps.hand) + (1 if ps.draw_tile else 0),
            "seat_wind": seat_winds[wind_offset],
        }
        if i == 0:
            p["hand"] = sort_tiles(ps.hand)
            p["draw_tile"] = ps.draw_tile
        d["players"].append(p)
    d["hand"] = sort_tiles(state.players[0].hand)
    d["draw_tile"] = state.players[0].draw_tile
    return d


def parse_ws_action(data: dict, available: list[Action]) -> Action:
    """Match a WebSocket action message to an available engine Action."""
    action_type = data.get("action_type", "")
    tile = data.get("tile")

    for a in available:
        if a.type.value == action_type:
            if a.type == ActionType.DISCARD:
                if a.tile == tile:
                    return a
            elif a.type == ActionType.CHI:
                req_meld = data.get("meld_tiles")
                if req_meld and sorted(req_meld) == sorted(a.meld_tiles):
                    return a
            elif a.type == ActionType.RIICHI:
                if a.tile == tile:
                    return a
            else:
                return a

    # Fallback: skip or first available
    for a in available:
        if a.type == ActionType.SKIP:
            return a
    return available[0]

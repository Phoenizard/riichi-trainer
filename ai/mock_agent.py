"""
Mock AI agent: makes simple heuristic-based decisions.
Used as placeholder until Mortal is integrated.
"""

from __future__ import annotations
import random
from collections import Counter

from game.engine import Action, ActionType, RoundState, PlayerState
from game.tiles import normalize, tile_number, tile_suit, is_red, sort_tiles, YAOCHUU


class MockAgent:
    """Simple heuristic AI for testing. Not strong, but plays legally."""

    def __init__(self, name: str = "AI"):
        self.name = name

    def choose_action(
        self,
        player_id: int,
        game_state: RoundState,
        available_actions: list[Action],
    ) -> Action:
        action_types = {a.type for a in available_actions}

        # Always tsumo if possible
        if ActionType.TSUMO in action_types:
            return next(a for a in available_actions if a.type == ActionType.TSUMO)

        # Always ron if possible
        if ActionType.RON in action_types:
            return next(a for a in available_actions if a.type == ActionType.RON)

        # Consider pon for yakuhai or if close to tenpai
        if ActionType.PON in action_types:
            pon_action = next(a for a in available_actions if a.type == ActionType.PON)
            tile = pon_action.tile
            base = normalize(tile)
            # Pon yakuhai tiles
            if base in YAOCHUU:
                if random.random() < 0.7:
                    return pon_action

        # Skip chi most of the time (simplified)
        if ActionType.CHI in action_types:
            if random.random() < 0.3:
                chi_actions = [a for a in available_actions if a.type == ActionType.CHI]
                if chi_actions:
                    return chi_actions[0]

        # Riichi if available (simplified: always riichi)
        riichi_actions = [a for a in available_actions if a.type == ActionType.RIICHI]
        if riichi_actions:
            if random.random() < 0.8:
                return riichi_actions[0]

        # Discard: simple tile efficiency heuristic
        discard_actions = [a for a in available_actions if a.type == ActionType.DISCARD]
        if discard_actions:
            return self._choose_discard(game_state.players[player_id], discard_actions)

        # Skip by default
        skip = [a for a in available_actions if a.type == ActionType.SKIP]
        if skip:
            return skip[0]

        return available_actions[0]

    def _choose_discard(self, ps: PlayerState, actions: list[Action]) -> Action:
        """Heuristic discard selection."""
        tiles = ps.closed_tiles
        counts = Counter(normalize(t) for t in tiles)

        best_action = None
        worst_score = float('inf')

        for action in actions:
            tile = action.tile
            base = normalize(tile)
            score = self._tile_value(base, counts)
            if score < worst_score:
                worst_score = score
                best_action = action

        return best_action or actions[0]

    def _tile_value(self, tile: str, counts: Counter) -> float:
        """Score a tile's value (higher = more useful to keep)."""
        score = 0.0

        # Pairs and trips are valuable
        cnt = counts.get(tile, 0)
        score += cnt * 3

        # Connected tiles (sequences)
        suit = tile_suit(tile)
        num = tile_number(tile)
        if suit and num:
            for delta in [-2, -1, 1, 2]:
                neighbor = num + delta
                if 1 <= neighbor <= 9:
                    n_tile = f"{neighbor}{suit}"
                    if counts.get(n_tile, 0) > 0:
                        score += 2 if abs(delta) == 1 else 1

            # Edge / terminal penalty
            if num in (1, 9):
                score -= 1
            elif num in (2, 8):
                score -= 0.5

        # Isolated honors are bad
        if tile in YAOCHUU and cnt <= 1:
            score -= 2

        return score

    def on_event(self, event: dict) -> None:
        """Receive game event (no-op for mock agent)."""
        pass

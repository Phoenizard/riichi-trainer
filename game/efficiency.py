"""
Tile efficiency analysis for Riichi Mahjong.

Calculates which discards reduce shanten and what acceptance tiles result,
considering visible tiles on the field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from mahjong.shanten import Shanten

from game.tiles import normalize


# Mapping from our mjai tile notation to 34-format index.
# 34-format: 0-8 = 1m-9m, 9-17 = 1p-9p, 18-26 = 1s-9s,
#            27-30 = E/S/W/N, 31-33 = P/F/C
_TILE_TO_34: dict[str, int] = {}
for i in range(1, 10):
    _TILE_TO_34[f"{i}m"] = i - 1
    _TILE_TO_34[f"{i}p"] = i + 8
    _TILE_TO_34[f"{i}s"] = i + 17
_TILE_TO_34["E"] = 27
_TILE_TO_34["S"] = 28
_TILE_TO_34["W"] = 29
_TILE_TO_34["N"] = 30
_TILE_TO_34["P"] = 31
_TILE_TO_34["F"] = 32
_TILE_TO_34["C"] = 33

# Reverse mapping: 34-index -> mjai tile string
_34_TO_TILE: dict[int, str] = {v: k for k, v in _TILE_TO_34.items()}

_shanten_calc = Shanten()


@dataclass
class EfficiencyRow:
    """One row in the efficiency table: discard X -> accept tiles Y."""
    discard: str                       # Tile to discard (mjai notation)
    accepts: list[str] = field(default_factory=list)  # Tiles that reduce shanten
    total: int = 0                     # Theoretical max acceptance count (types * 4)
    remaining: int = 0                 # Remaining after subtracting visible tiles


def tiles_to_34_array(tiles: list[str]) -> list[int]:
    """Convert mjai tile list to 34-format count array."""
    arr = [0] * 34
    for t in tiles:
        idx = _TILE_TO_34.get(normalize(t))
        if idx is not None:
            arr[idx] += 1
    return arr


def calculate_shanten(hand: list[str]) -> int:
    """Calculate shanten number for a 13-tile hand.

    Returns: -1 (complete/tenpai with 14), 0 (tenpai), 1+
    """
    arr = tiles_to_34_array(hand)
    return _shanten_calc.calculate_shanten(arr)


def calculate_efficiency(
    hand: list[str],
    visible_tiles: list[str],
) -> list[EfficiencyRow]:
    """Calculate tile efficiency for a 14-tile hand.

    For each possible discard, determines which tiles would reduce shanten,
    their theoretical count, and remaining count after visible tiles.

    Args:
        hand: 14-tile hand (13 + draw) in mjai notation.
        visible_tiles: All tiles visible on the field (discards, melds,
                      dora indicators) -- NOT including the player's own hand.

    Returns:
        List of EfficiencyRow sorted by total descending.
        Only includes discards where at least one acceptance tile exists.
    """
    if len(hand) < 14:
        return []

    # Count visible tiles (field only, not our hand)
    visible_counts = tiles_to_34_array(visible_tiles)

    # Get unique discard candidates (normalized to avoid duplicate rows)
    seen_normalized: set[str] = set()
    discard_candidates: list[str] = []
    for t in hand:
        n = normalize(t)
        if n not in seen_normalized:
            seen_normalized.add(n)
            discard_candidates.append(t)

    rows: list[EfficiencyRow] = []

    for discard in discard_candidates:
        # Build 13-tile hand after discarding
        remaining_hand = list(hand)
        remaining_hand.remove(discard)
        arr13 = tiles_to_34_array(remaining_hand)
        shanten_after_discard = _shanten_calc.calculate_shanten(arr13)

        # Find acceptance tiles: tiles that would reduce shanten by 1
        accepts: list[str] = []
        total_count = 0
        remaining_count = 0

        for idx in range(34):
            # Can we draw this tile? Max 4 per tile type.
            if arr13[idx] >= 4:
                continue

            # Simulate drawing this tile
            arr13[idx] += 1
            new_shanten = _shanten_calc.calculate_shanten(arr13)
            arr13[idx] -= 1

            if new_shanten < shanten_after_discard:
                tile_str = _34_TO_TILE[idx]
                accepts.append(tile_str)
                # Theoretical: 4 copies minus copies in our 13-tile hand
                copies_available = 4 - arr13[idx]
                total_count += copies_available
                # Remaining: also subtract visible tiles
                copies_remaining = copies_available - visible_counts[idx]
                remaining_count += max(0, copies_remaining)

        if accepts:
            rows.append(EfficiencyRow(
                discard=discard,
                accepts=accepts,
                total=total_count,
                remaining=remaining_count,
            ))

    # Sort by total descending, then remaining descending as tiebreaker
    rows.sort(key=lambda r: (r.total, r.remaining), reverse=True)
    return rows

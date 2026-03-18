"""
Tile definitions and utilities for Riichi Mahjong.

Tile notation (mjai-compatible):
  Man (万子): "1m" - "9m", "0m" (red five)
  Pin (筒子): "1p" - "9p", "0p" (red five)
  Sou (索子): "1s" - "9s", "0s" (red five)
  Wind (風牌): "E" (東), "S" (南), "W" (西), "N" (北)
  Dragon (三元牌): "P" (白), "F" (發), "C" (中)
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import random


class TileType(Enum):
    MAN = "m"
    PIN = "p"
    SOU = "s"
    WIND = "wind"
    DRAGON = "dragon"


# All unique tile faces (without red fives)
MANS = [f"{i}m" for i in range(1, 10)]
PINS = [f"{i}p" for i in range(1, 10)]
SOUS = [f"{i}s" for i in range(1, 10)]
WINDS = ["E", "S", "W", "N"]
DRAGONS = ["P", "F", "C"]

TERMINALS = {"1m", "9m", "1p", "9p", "1s", "9s"}
HONORS = set(WINDS + DRAGONS)
YAOCHUU = TERMINALS | HONORS  # terminals + honors

SUIT_TILES = MANS + PINS + SOUS
ALL_TILE_FACES = SUIT_TILES + WINDS + DRAGONS

# Mapping for display
TILE_DISPLAY = {
    "1m": "一万", "2m": "二万", "3m": "三万", "4m": "四万", "5m": "五万",
    "6m": "六万", "7m": "七万", "8m": "八万", "9m": "九万", "0m": "赤五万",
    "1p": "一筒", "2p": "二筒", "3p": "三筒", "4p": "四筒", "5p": "五筒",
    "6p": "六筒", "7p": "七筒", "8p": "八筒", "9p": "九筒", "0p": "赤五筒",
    "1s": "一索", "2s": "二索", "3s": "三索", "4s": "四索", "5s": "五索",
    "6s": "六索", "7s": "七索", "8s": "八索", "9s": "九索", "0s": "赤五索",
    "E": "東", "S": "南", "W": "西", "N": "北",
    "P": "白", "F": "發", "C": "中",
}

# Unicode tile rendering (for terminal UI)
TILE_UNICODE = {
    "1m": "🀇", "2m": "🀈", "3m": "🀉", "4m": "🀊", "5m": "🀋",
    "6m": "🀌", "7m": "🀍", "8m": "🀎", "9m": "🀏", "0m": "🀋",
    "1p": "🀙", "2p": "🀚", "3p": "🀛", "4p": "🀜", "5p": "🀝",
    "6p": "🀞", "7p": "🀟", "8p": "🀠", "9p": "🀡", "0p": "🀝",
    "1s": "🀐", "2s": "🀑", "3s": "🀒", "4s": "🀓", "5s": "🀔",
    "6s": "🀕", "7s": "🀖", "8s": "🀗", "9s": "🀘", "0s": "🀔",
    "E": "🀀", "S": "🀁", "W": "🀂", "N": "🀃",
    "P": "🀆", "F": "🀅", "C": "🀄",
}

WIND_NAMES = {0: "E", 1: "S", 2: "W", 3: "N"}
WIND_KANJI = {"E": "東", "S": "南", "W": "西", "N": "北"}


def build_wall(red_fives: bool = True) -> list[str]:
    """Build a shuffled 136-tile wall.

    Args:
        red_fives: If True, include one red five per suit (standard rules).
    """
    wall = []
    for face in ALL_TILE_FACES:
        wall.extend([face] * 4)

    if red_fives:
        # Replace one regular 5 with red 5 in each suit
        for suit in ["m", "p", "s"]:
            idx = wall.index(f"5{suit}")
            wall[idx] = f"0{suit}"

    random.shuffle(wall)
    return wall


def tile_type(tile: str) -> TileType:
    """Get the type of a tile."""
    if tile in WINDS:
        return TileType.WIND
    if tile in DRAGONS:
        return TileType.DRAGON
    return TileType(tile[-1])


def tile_number(tile: str) -> int | None:
    """Get the numeric value of a suited tile. Returns None for honors."""
    if tile in WINDS or tile in DRAGONS:
        return None
    n = int(tile[0])
    return 5 if n == 0 else n  # red five → 5


def tile_suit(tile: str) -> str | None:
    """Get suit character ('m','p','s') or None for honors."""
    if tile in WINDS or tile in DRAGONS:
        return None
    return tile[-1]


def is_red(tile: str) -> bool:
    """Check if tile is a red five."""
    return tile[0] == "0"


def normalize(tile: str) -> str:
    """Normalize red five to regular five for pattern matching."""
    if is_red(tile):
        return f"5{tile[-1]}"
    return tile


def sort_tiles(tiles: list[str]) -> list[str]:
    """Sort tiles in standard order: man → pin → sou → wind → dragon."""
    order = {face: i for i, face in enumerate(ALL_TILE_FACES)}
    # Red fives sort with their regular counterpart but come first
    def sort_key(t):
        base = normalize(t)
        idx = order.get(base, 999)
        return (idx, 0 if is_red(t) else 1)
    return sorted(tiles, key=sort_key)


def tiles_to_136(tiles: list[str]) -> list[int]:
    """Convert tile strings to 136-format indices (for mahjong library).

    The mahjong library uses 136-tile indices where each tile face has 4 indices.
    Red fives always use the first index of their face (e.g., 16 for 0m/5mr).
    Regular copies start from index 1 if a red five of the same face exists.
    """
    result = []
    # Track used indices per face to avoid collisions
    used: dict[str, list[int]] = {}

    # Check which faces have red fives so we can reserve index 0 for them
    has_red: set[str] = set()
    for tile in tiles:
        if is_red(tile):
            has_red.add(normalize(tile))

    for tile in tiles:
        base = normalize(tile)
        face_idx = ALL_TILE_FACES.index(base)

        if is_red(tile):
            idx_136 = face_idx * 4  # red five always gets index 0
        else:
            # Find next available copy index, skipping 0 if reserved for red
            start = 1 if base in has_red else 0
            face_used = used.get(base, [])
            copy = start
            while face_idx * 4 + copy in face_used:
                copy += 1
            idx_136 = face_idx * 4 + copy

        used.setdefault(base, []).append(idx_136)
        result.append(idx_136)
    return result


def tile_to_display(tile: str, use_unicode: bool = False, color: bool = True) -> str:
    """Get display string for a tile, optionally with ANSI color.

    Colors: man=red, pin=blue, sou=green, wind=default, dragon=per-tile,
    red fives=bold red.
    """
    if use_unicode:
        prefix = "🟥" if is_red(tile) else ""
        text = prefix + TILE_UNICODE.get(tile, tile)
    else:
        prefix = "*" if is_red(tile) else ""
        text = prefix + TILE_DISPLAY.get(tile, tile)

    if not color:
        return text

    RST = "\033[0m"
    if is_red(tile):
        return f"\033[1;31m{text}{RST}"  # bold red
    t = tile_type(tile)
    if t == TileType.MAN:
        return f"\033[31m{text}{RST}"    # red
    if t == TileType.PIN:
        return f"\033[34m{text}{RST}"    # blue
    if t == TileType.SOU:
        return f"\033[32m{text}{RST}"    # green
    if t == TileType.DRAGON:
        if tile == "C":
            return f"\033[31m{text}{RST}"  # red (中)
        if tile == "F":
            return f"\033[1;32m{text}{RST}"  # bright green (發)
        return text  # white (白) — default color
    return text  # winds — default color


def hand_to_display(tiles: list[str], use_unicode: bool = False, sep: str = " ") -> str:
    """Display a hand of tiles."""
    return sep.join(tile_to_display(t, use_unicode) for t in sort_tiles(tiles))


def dora_from_indicator(indicator: str) -> str:
    """Given a dora indicator tile, return the actual dora tile.

    Rules: Next tile in sequence. For suits: wraps 9→1.
    For winds: E→S→W→N→E. For dragons: P→F→C→P.
    Red five indicators: treat as 5.
    """
    ind = normalize(indicator)

    if ind in WINDS:
        wind_order = WINDS
        idx = wind_order.index(ind)
        return wind_order[(idx + 1) % 4]

    if ind in DRAGONS:
        dragon_order = DRAGONS
        idx = dragon_order.index(ind)
        return dragon_order[(idx + 1) % 3]

    # Suited tile
    suit = ind[-1]
    num = int(ind[0])
    next_num = num % 9 + 1
    return f"{next_num}{suit}"

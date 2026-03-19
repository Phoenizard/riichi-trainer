# Tile Efficiency Panel Design

## Overview

A collapsible panel below the hand area that shows tile efficiency analysis for each possible discard. Helps players understand which discards maximize their acceptance count (进张) toward reducing shanten.

## Layout

Position in page hierarchy (top to bottom):
1. Game info bar
2. Table area (opponents, discard ponds, center info)
3. Hand area (hand tiles + draw tile + melds + action bar)
4. Coach panel (AI recommendations, orange theme)
5. **Tile efficiency panel** (purple theme `#8e44ad`, collapsible)

## Panel Structure

### Header (clickable toggle)
- Left: "牌效率分析" with icon
- Right: current shanten badge (green pill) + collapse arrow

### Table (visible when expanded)

| Column | Content | Notes |
|--------|---------|-------|
| 切 | Small tile component | The tile to discard |
| 进张 | Mini tile components | All acceptance tiles that reduce shanten |
| 总进张 | Number | Theoretical max count (each tile type × 4) |
| 剩余 | Number (colored) | Remaining = total − visible on field |

### Sorting & Filtering
- **Sort**: by 总进张 descending
- **Filter**: only show discards that reduce shanten (not maintain)
- **Highlight**: best row gets light purple background (`#f8f4ff`)

### Legend
Below table: brief explanation of 总进张 vs 剩余 columns.

## Data Flow

### Backend Computation

New module `game/efficiency.py`:

```python
def calculate_efficiency(hand: list[str], visible_tiles: list[str]) -> list[EfficiencyRow]
```

1. Calculate current shanten of the full hand (14 tiles)
2. For each tile in hand, simulate discarding it (13 tiles remain)
3. For the 13-tile hand, find all tiles that would reduce shanten by 1
4. Count theoretical total (tile_types × 4) and remaining (total − visible count)
5. Only include rows where post-discard shanten < current shanten OR where accepting tiles exist
6. Sort by total acceptance count descending

### Shanten Calculation

Use the `mahjong` library's `Shanten` class (already a project dependency):

```python
from mahjong.shanten import Shanten
from mahjong.tile import TilesConverter
```

Convert our mjai tile format → 136-format → call `shanten.calculate_shanten()`.

### Visible Tiles Collection

Gather from `RoundState`:
- All 4 players' discards (`player.discards`)
- All 4 players' open meld tiles (`player.melds[*].tiles`)
- Dora indicators (`state.dora_indicators`)
- Player's own hand (to avoid double-counting)

### WebSocket Integration

Add efficiency data to the `action_required` message (only when player needs to discard):

```python
{
    "type": "action_required",
    "actions": [...],
    "efficiency": [
        {
            "discard": "7m",
            "accepts": ["1s", "4s", "5s", "6s", "9s", "E"],
            "total": 24,
            "remaining": 19
        },
        ...
    ],
    "shanten": 1
}
```

### Frontend Component

New component `EfficiencyPanel.tsx`:
- Receives `efficiency` data and `shanten` from state
- Collapsible with `localStorage` persistence for open/closed state
- Uses existing `<Tile small>` component for discard column
- Uses a new `<Tile mini>` size for acceptance tiles (24×34px)
- Purple accent color theme to differentiate from coach panel

## Technical Decisions

- **Shanten library**: `mahjong` (already installed) — its `Shanten` class operates on 136-format tile arrays
- **Computation location**: Backend (Python), sent with `action_required` — avoids duplicating tile logic in frontend
- **Performance**: ~34 discard candidates × full shanten check each. Shanten calculation is fast (<1ms each), so total <50ms per turn. No caching needed.
- **Only on discard turns**: efficiency data is only relevant when the player chooses which tile to discard, not during call decisions

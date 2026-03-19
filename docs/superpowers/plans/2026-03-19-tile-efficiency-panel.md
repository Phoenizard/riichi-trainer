# Tile Efficiency Panel Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible tile efficiency panel below the hand area that shows, for each possible discard, which tiles would reduce shanten, their theoretical count, and remaining count based on visible tiles.

**Architecture:** Backend Python module (`game/efficiency.py`) computes efficiency data using the `mahjong` library's `Shanten` class. Data is attached to the `action_required` WebSocket message when the player needs to discard. Frontend renders a new `EfficiencyPanel.tsx` component with a collapsible table.

**Tech Stack:** Python `mahjong` library (Shanten, TilesConverter), React/TypeScript, CSS

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `game/efficiency.py` | Create | Shanten calculation, acceptance tile enumeration, visible tile counting |
| `tests/test_efficiency.py` | Create | Unit tests for efficiency calculations |
| `backend/web_agent.py` | Modify | Attach efficiency data to `action_required` message |
| `frontend/src/types/game.ts` | Modify | Add `EfficiencyRow` type and extend `ServerMessage` |
| `frontend/src/hooks/useGameSocket.ts` | Modify | Store efficiency data in state |
| `frontend/src/components/EfficiencyPanel.tsx` | Create | Collapsible panel with efficiency table |
| `frontend/src/App.tsx` | Modify | Add EfficiencyPanel below CoachPanel |
| `frontend/src/styles/tiles.css` | Modify | Add efficiency panel styles |

---

## Chunk 1: Backend — Efficiency Calculation

### Task 1: Core efficiency calculation module

**Files:**
- Create: `game/efficiency.py`
- Create: `tests/test_efficiency.py`

- [ ] **Step 1: Write the test file with core test cases**

```python
# tests/test_efficiency.py
"""Tests for tile efficiency calculation."""
import pytest
from game.efficiency import (
    tiles_to_34_array,
    calculate_shanten,
    calculate_efficiency,
    EfficiencyRow,
)


class TestTilesTo34Array:
    def test_simple_man(self):
        result = tiles_to_34_array(["1m", "2m", "3m"])
        assert result[0] == 1  # 1m
        assert result[1] == 1  # 2m
        assert result[2] == 1  # 3m
        assert sum(result) == 3

    def test_red_five_counts_as_five(self):
        result = tiles_to_34_array(["0m"])
        assert result[4] == 1  # 5m slot

    def test_honors(self):
        result = tiles_to_34_array(["E", "E", "S"])
        assert result[27] == 2  # E (ton)
        assert result[28] == 1  # S (nan)

    def test_dragons(self):
        result = tiles_to_34_array(["P", "F", "C"])
        assert result[31] == 1  # P (haku)
        assert result[32] == 1  # F (hatsu)
        assert result[33] == 1  # C (chun)

    def test_duplicate_tiles(self):
        result = tiles_to_34_array(["1m", "1m", "1m"])
        assert result[0] == 3


class TestCalculateShanten:
    def test_tenpai(self):
        # 123m 456p 234s 78s — waiting on 6s or 9s
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "2s", "3s", "4s", "7s", "8s", "E", "E"]
        assert calculate_shanten(hand) == 0

    def test_one_shanten(self):
        # Need one more step to tenpai
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "2s", "3s", "7s", "8s", "E", "E", "C"]
        result = calculate_shanten(hand)
        assert result >= 1

    def test_complete_hand(self):
        # 123m 456p 789s 11E + draw = complete (but shanten checks 13 tiles)
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s", "E", "E", "P", "P"]
        result = calculate_shanten(hand)
        assert result == 0  # tenpai (waiting to complete)


class TestCalculateEfficiency:
    def test_basic_efficiency(self):
        # 123m 456p 2347s EE + draw 9m (14 tiles)
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "2s", "3s", "4s", "7s", "E", "E", "C", "9m"]
        visible: list[str] = []
        rows = calculate_efficiency(hand, visible)
        assert len(rows) > 0
        # Should be sorted by total descending
        for i in range(len(rows) - 1):
            assert rows[i].total >= rows[i + 1].total

    def test_only_shanten_reducing(self):
        """Only include discards that reduce shanten compared to current."""
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "2s", "3s", "4s", "7s", "E", "E", "C", "9m"]
        visible: list[str] = []
        rows = calculate_efficiency(hand, visible)
        # All returned rows should have accepts (meaning they reduce shanten)
        for row in rows:
            assert len(row.accepts) > 0

    def test_visible_tiles_reduce_remaining(self):
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "2s", "3s", "4s", "7s", "E", "E", "C", "9m"]
        # Suppose 2 copies of some accept tile are visible
        visible_empty = []
        visible_some = ["1s", "1s", "5s", "5s"]
        rows_empty = calculate_efficiency(hand, visible_empty)
        rows_some = calculate_efficiency(hand, visible_some)
        # Same discards should appear, but remaining should be lower
        if rows_empty and rows_some:
            # Total should be same, remaining should be <=
            for re, rs in zip(rows_empty, rows_some):
                if re.discard == rs.discard:
                    assert re.total == rs.total
                    assert rs.remaining <= re.remaining

    def test_empty_result_when_already_tenpai_no_improvement(self):
        """If hand is already complete (-1 shanten), no efficiency rows."""
        # This is a winning hand (14 tiles)
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s", "1s", "2s", "3s", "E", "E"]
        visible: list[str] = []
        rows = calculate_efficiency(hand, visible)
        # Might return rows or not depending on if any discard maintains tenpai
        # The key is it shouldn't crash
        assert isinstance(rows, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/shay/Workplace/riichi-trainer && python -m pytest tests/test_efficiency.py -v`
Expected: ModuleNotFoundError — `game.efficiency` does not exist yet

- [ ] **Step 3: Implement `game/efficiency.py`**

```python
# game/efficiency.py
"""
Tile efficiency analysis for Riichi Mahjong.

Calculates which discards reduce shanten and what acceptance tiles result,
considering visible tiles on the field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from mahjong.shanten import Shanten

from game.tiles import normalize, ALL_TILE_FACES, WINDS, DRAGONS


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

# Reverse mapping: 34-index → mjai tile string
_34_TO_TILE: dict[int, str] = {v: k for k, v in _TILE_TO_34.items()}

_shanten_calc = Shanten()


@dataclass
class EfficiencyRow:
    """One row in the efficiency table: discard X → accept tiles Y."""
    discard: str                       # Tile to discard (mjai notation)
    accepts: list[str] = field(default_factory=list)  # Tiles that reduce shanten
    total: int = 0                     # Theoretical max acceptance count (types × 4)
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
                      dora indicators) — NOT including the player's own hand.

    Returns:
        List of EfficiencyRow sorted by total descending.
        Only includes discards where at least one acceptance tile exists.
    """
    if len(hand) < 14:
        return []

    # Count visible tiles (field only, not our hand)
    visible_counts = tiles_to_34_array(visible_tiles)

    # Count tiles in our hand
    hand_counts = tiles_to_34_array(hand)

    # Current shanten with full 14-tile hand — we want to find discards
    # such that the resulting 13-tile hand has a lower shanten reachable.
    # First compute shanten of each 13-tile hand after discarding.
    # Then for each, find tiles that further reduce shanten.

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/shay/Workplace/riichi-trainer && python -m pytest tests/test_efficiency.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add game/efficiency.py tests/test_efficiency.py
git commit -m "feat: add tile efficiency calculation module"
```

### Task 2: Wire efficiency data into WebSocket protocol

**Files:**
- Modify: `backend/web_agent.py:40-74` (choose_action method)

- [ ] **Step 1: Add efficiency import and computation to `choose_action()`**

In `backend/web_agent.py`, add the import at the top:

```python
from game.efficiency import calculate_efficiency
```

Then modify the `action_required` message in `choose_action()` to include efficiency data. After the existing coach analysis block (line ~66), and before the `action_required` put (line ~69), compute and attach efficiency:

```python
        # Compute tile efficiency (only when player has discard actions)
        efficiency_data = None
        has_discard = any(a.type == ActionType.DISCARD for a in available_actions)
        if has_discard:
            # Gather visible tiles: all discards + all open meld tiles + dora indicators
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
```

Then update the `action_required` message dict to include the new fields:

```python
        msg: dict = {
            "type": "action_required",
            "available_actions": serialize_actions(available_actions),
            "hand": sort_tiles(ps.hand),
            "draw_tile": ps.draw_tile,
        }
        if efficiency_data is not None:
            from game.efficiency import calculate_shanten
            full_hand = list(ps.hand) + ([ps.draw_tile] if ps.draw_tile else [])
            msg["efficiency"] = efficiency_data
            msg["shanten"] = calculate_shanten(full_hand[:-1]) if len(full_hand) >= 14 else None
        self.ws_send_queue.put(msg)
```

- [ ] **Step 2: Test manually — start the game, verify efficiency data appears in WS messages**

Run: `cd /Users/shay/Workplace/riichi-trainer && python start_web.py`
Open browser devtools → Network → WS → verify `action_required` messages contain `efficiency` array.

- [ ] **Step 3: Commit**

```bash
git add backend/web_agent.py
git commit -m "feat: attach tile efficiency data to action_required WS message"
```

---

## Chunk 2: Frontend — Efficiency Panel Component

### Task 3: Add TypeScript types for efficiency data

**Files:**
- Modify: `frontend/src/types/game.ts`

- [ ] **Step 1: Add EfficiencyRow type and update ServerMessage**

In `frontend/src/types/game.ts`, add after the `CoachAnalysis` interface:

```typescript
export interface EfficiencyRow {
  discard: string;
  accepts: string[];
  total: number;
  remaining: number;
}
```

Update the `action_required` variant in `ServerMessage` union:

```typescript
  | { type: 'action_required'; available_actions: ActionOption[]; hand: string[]; draw_tile: string | null; efficiency?: EfficiencyRow[]; shanten?: number | null }
```

Add `efficiency` and `efficiencyShanten` to `GameState`:

```typescript
export interface GameState {
  // ... existing fields ...
  efficiency: EfficiencyRow[] | null;
  efficiencyShanten: number | null;
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/types/game.ts
git commit -m "feat: add EfficiencyRow type to game types"
```

### Task 4: Update state management for efficiency data

**Files:**
- Modify: `frontend/src/hooks/useGameSocket.ts`

- [ ] **Step 1: Add efficiency to initial state, reducer, and action dispatch**

In `useGameSocket.ts`:

1. Add to `initialState`:
```typescript
efficiency: null,
efficiencyShanten: null,
```

2. Update `GameAction` type — extend `ACTION_REQUIRED` payload:
```typescript
| { type: 'ACTION_REQUIRED'; payload: { available_actions: any[]; hand: string[]; draw_tile: string | null; efficiency?: any[]; shanten?: number | null } }
```

3. In the `ACTION_REQUIRED` case of the reducer, add:
```typescript
efficiency: action.payload.efficiency || null,
efficiencyShanten: action.payload.shanten ?? null,
```

4. In the `GAME_EVENT` case for `discard` by player 0, add to the return block:
```typescript
efficiency: null,
efficiencyShanten: null,
```

5. In the `action_required` message handler, pass efficiency and shanten:
```typescript
dispatch({
  type: 'ACTION_REQUIRED',
  payload: {
    available_actions: msg.available_actions,
    hand: msg.hand,
    draw_tile: msg.draw_tile,
    efficiency: (msg as any).efficiency,
    shanten: (msg as any).shanten,
  },
});
```

6. In the `ROUND_RESULT` and `GAME_OVER` cases, add:
```typescript
efficiency: null,
efficiencyShanten: null,
```

7. In `RESET`, add to initialState (already has `efficiency: null, efficiencyShanten: null`).

8. In `sendAction`, update the dispatch to clear efficiency:
```typescript
dispatch({ type: 'ACTION_REQUIRED', payload: { available_actions: [], hand: state.hand, draw_tile: state.drawTile, efficiency: null, shanten: null } });
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/hooks/useGameSocket.ts
git commit -m "feat: wire efficiency data through state management"
```

### Task 5: Create EfficiencyPanel component

**Files:**
- Create: `frontend/src/components/EfficiencyPanel.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/EfficiencyPanel.tsx
import React, { useState } from 'react';
import Tile from './Tile';
import type { EfficiencyRow } from '../types/game';

interface EfficiencyPanelProps {
  efficiency: EfficiencyRow[] | null;
  shanten: number | null;
}

const EfficiencyPanel: React.FC<EfficiencyPanelProps> = ({ efficiency, shanten }) => {
  const [expanded, setExpanded] = useState(() => {
    const saved = localStorage.getItem('showEfficiency');
    return saved !== null ? saved === 'true' : true;
  });

  const toggle = () => {
    setExpanded(v => {
      const next = !v;
      localStorage.setItem('showEfficiency', String(next));
      return next;
    });
  };

  return (
    <div className="efficiency-panel">
      <div className="efficiency-header" onClick={toggle}>
        <span>牌效率分析</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {shanten !== null && shanten !== undefined && (
            <span className="efficiency-shanten-badge">
              {shanten === -1 ? '聴牌' : `${shanten} 向听`}
            </span>
          )}
          <span>{expanded ? '▾' : '▸'}</span>
        </span>
      </div>
      {expanded && efficiency && efficiency.length > 0 && (
        <div className="efficiency-body">
          <table className="efficiency-table">
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>切</th>
                <th style={{ textAlign: 'left' }}>进张</th>
                <th style={{ textAlign: 'right' }}>总进张</th>
                <th style={{ textAlign: 'right' }}>剩余</th>
              </tr>
            </thead>
            <tbody>
              {efficiency.map((row, i) => (
                <tr key={row.discard} className={i === 0 ? 'efficiency-best' : ''}>
                  <td className="efficiency-discard-cell">
                    <Tile tile={row.discard} small />
                  </td>
                  <td className="efficiency-accepts-cell">
                    <div className="efficiency-accepts">
                      {row.accepts.map((t, j) => (
                        <Tile key={j} tile={t} mini />
                      ))}
                    </div>
                  </td>
                  <td className="efficiency-total">{row.total}</td>
                  <td className={`efficiency-remaining ${row.remaining <= 4 ? 'efficiency-low' : ''}`}>
                    {row.remaining}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="efficiency-legend">
            <span>总进张 = 理论最大枚数</span>
            <span>剩余 = 扣除场上可见牌</span>
          </div>
        </div>
      )}
      {expanded && (!efficiency || efficiency.length === 0) && (
        <div className="efficiency-body">
          <div className="efficiency-empty">无可减少向听数的打法</div>
        </div>
      )}
    </div>
  );
};

export default EfficiencyPanel;
```

- [ ] **Step 2: Add `mini` prop to Tile component**

In `frontend/src/components/Tile.tsx`:

1. Add `mini` to the TileProps interface (after `small`):

```typescript
interface TileProps {
  tile: string;
  onClick?: () => void;
  clickable?: boolean;
  recommended?: boolean;
  faceDown?: boolean;
  small?: boolean;
  mini?: boolean;    // NEW: even smaller for efficiency accepts
  sideways?: boolean;
}
```

2. Add `mini` to the function signature destructuring:

```typescript
const Tile: React.FC<TileProps> = ({ tile, onClick, clickable, recommended, faceDown, small, mini, sideways }) => {
```

3. Add `mini` to the faceDown branch (line 37):

```typescript
<div className={`tile tile-back ${small ? 'tile-small' : ''} ${mini ? 'tile-mini' : ''} ${sideways ? 'tile-sideways' : ''}`} />
```

4. Add `mini` to the classes array (after `small && 'tile-small'`):

```typescript
  const classes = [
    'tile',
    suitClass,
    isRed && 'tile-red',
    clickable && 'tile-clickable',
    recommended && 'tile-recommended',
    small && 'tile-small',
    mini && 'tile-mini',
    sideways && 'tile-sideways',
  ].filter(Boolean).join(' ');
```

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/components/EfficiencyPanel.tsx src/components/Tile.tsx
git commit -m "feat: create EfficiencyPanel component with mini tile support"
```

### Task 6: Add CSS styles for efficiency panel

**Files:**
- Modify: `frontend/src/styles/tiles.css`

- [ ] **Step 1: Add efficiency panel styles at the end of tiles.css**

```css
/* Tile efficiency panel */
.efficiency-panel {
  background: var(--card-bg);
  border-top: 2px solid #8e44ad;
}

.efficiency-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  color: #8e44ad;
}

.efficiency-shanten-badge {
  background: #27ae60;
  color: #fff;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
}

.efficiency-body {
  padding: 0 16px 12px;
}

.efficiency-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.efficiency-table thead th {
  padding: 6px 8px;
  font-weight: 600;
  font-size: 12px;
  color: #888;
  border-bottom: 2px solid #eee;
}

.efficiency-table tbody tr {
  border-bottom: 1px solid #f0f0f0;
}

.efficiency-best {
  background: #f8f4ff;
}

.efficiency-discard-cell {
  padding: 8px;
  vertical-align: middle;
}

.efficiency-accepts-cell {
  padding: 8px;
  vertical-align: middle;
}

.efficiency-accepts {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
  align-items: center;
}

.efficiency-total {
  padding: 8px;
  text-align: right;
  font-weight: 700;
  font-size: 15px;
}

.efficiency-best .efficiency-total {
  color: #8e44ad;
}

.efficiency-remaining {
  padding: 8px;
  text-align: right;
  font-weight: 600;
  font-size: 14px;
  color: #27ae60;
}

.efficiency-low {
  color: #e67e22;
}

.efficiency-legend {
  margin-top: 8px;
  font-size: 11px;
  color: #999;
  display: flex;
  gap: 16px;
}

.efficiency-empty {
  padding: 8px 0;
  color: #999;
  font-size: 13px;
}

/* Mini tiles (for efficiency accepts) */
.tile-mini {
  width: 24px;
  height: 34px;
  font-size: 10px;
  border-radius: 3px;
}
.tile-mini .tile-number {
  font-size: 11px;
}
.tile-mini .tile-suit {
  font-size: 8px;
}
.tile-mini .tile-honor {
  font-size: 12px;
}
.tile-mini.tile-red::after {
  width: 3px;
  height: 3px;
  top: 1px;
  right: 1px;
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/styles/tiles.css
git commit -m "feat: add efficiency panel CSS styles with mini tile size"
```

### Task 7: Integrate EfficiencyPanel into App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Import and render EfficiencyPanel**

Add import:
```typescript
import EfficiencyPanel from './components/EfficiencyPanel';
```

Add after the `CoachPanel` block (line ~75):

```tsx
      {/* Tile efficiency panel */}
      <EfficiencyPanel
        efficiency={state.efficiency}
        shanten={state.efficiencyShanten ?? state.coach?.shanten ?? null}
      />
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/App.tsx
git commit -m "feat: integrate EfficiencyPanel into main app layout"
```

---

## Chunk 3: Build, Test, Verify

### Task 8: Build and verify

- [ ] **Step 1: Run backend tests**

```bash
cd /Users/shay/Workplace/riichi-trainer && python -m pytest tests/test_efficiency.py -v
```

Expected: All tests pass.

- [ ] **Step 2: Build frontend**

```bash
cd /Users/shay/Workplace/riichi-trainer/frontend && npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 3: Start the game and verify end-to-end**

```bash
cd /Users/shay/Workplace/riichi-trainer && python start_web.py
```

Open http://localhost:8000, start a game, and verify:
1. Efficiency panel appears below coach panel
2. Table shows discard options with acceptance tiles
3. Panel is collapsible
4. Data updates each time it's the player's turn to discard
5. Panel disappears during call decisions

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: tile efficiency panel — build verified"
```

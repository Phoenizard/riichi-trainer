# Web UI Specification — Riichi Mahjong AI Trainer

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | FastAPI | Native WebSocket + async, zero migration cost from existing Python code |
| Frontend | React + TypeScript | Component-based, best for complex interactive UI |
| Build | Vite | Zero-config, fast HMR |
| Tile Rendering | CSS + HTML (div/span) | Simple, interactive, swap to images later via TileRenderer component |
| Communication | WebSocket | Real-time bidirectional game events |

## Architecture

### Threading Model

```
Main Thread (asyncio)           Engine Thread
┌───────────────────┐          ┌────────────────────┐
│ FastAPI + WS      │          │ GameEngine.play_*() │
│                   │  Queue   │ MortalAgent × 3     │
│ WebAgent ◄────────┼──────────┤ (blocking ~2s/turn) │
│ (async wait)      │          │                     │
└───────────────────┘          └────────────────────┘
```

- GameEngine runs in a **separate thread** (existing sync code, zero changes needed)
- WebAgent bridges via `threading.Event` + `queue.Queue`
- FastAPI main thread handles WebSocket + static files
- Mortal ~2s inference blocks engine thread only, WebSocket stays responsive

### WebSocket Protocol

```jsonc
// === Server → Client ===

// Game state update (every action)
{"type": "game_event", "event": {/* engine event: discard/draw/chi/pon/kan/reach... */}}

// Player must act
{"type": "action_required", "available_actions": [
  {"type": "discard", "tile": "3m"},
  {"type": "discard", "tile": "5p"},
  {"type": "riichi", "tile": "3m"},
  {"type": "tsumo"}
], "hand": ["1m","2m","3m",...], "draw_tile": "5p"}

// AI coach recommendation (sent alongside action_required)
{"type": "coach", "analysis": {
  "recommended": "3m",
  "shanten": 1,
  "candidates": [{"tile":"3m","score":0.89,"rank":1}, {"tile":"8s","score":0.06,"rank":2}]
}}

// Round result
{"type": "round_result", "result": "tsumo", "winner": 2, "han": 3, "fu": 30,
 "yaku": ["立直","一発","断么九"], "score_deltas": [0,-2000,-2000,6000]}

// Game info (scores, round, dora etc - sent at round start and on changes)
{"type": "game_info", "round_wind": "E", "round_number": 1, "honba": 0,
 "scores": [25000,25000,25000,25000], "dora_indicators": ["3s"],
 "tiles_remaining": 70, "dealer": 0}

// AI thinking indicator
{"type": "ai_thinking", "active": true}

// === Client → Server ===

// Player action
{"type": "action", "action_type": "discard", "tile": "3m"}

// Start new game
{"type": "new_game"}
```

### WebAgent Implementation

```python
class WebAgent:
    """Bridges async WebSocket ↔ sync GameEngine via threading primitives."""

    def __init__(self):
        self._action_event = threading.Event()
        self._chosen_action: Optional[Action] = None
        self._pending_state: Optional[dict] = None  # available_actions + state for WS push
        self.ws_send_queue = queue.Queue()  # engine thread → WS thread

    def choose_action(self, player_id, game_state, available_actions) -> Action:
        # Push to WS send queue (will be picked up by async WS handler)
        self.ws_send_queue.put({"type": "action_required", ...})
        # Block until player responds via WS
        self._action_event.clear()
        self._action_event.wait(timeout=300)  # 5 min timeout
        return self._chosen_action

    def receive_player_action(self, action_data: dict):
        # Called from WS handler when client sends action
        self._chosen_action = parse_action(action_data)
        self._action_event.set()

    def on_event(self, event):
        self.ws_send_queue.put({"type": "game_event", "event": event})
```

## UI Layout

### Desktop (min-width: 900px)

```
┌──────────────────────────────────────────────────────────────┐
│                     Game Info Bar                              │
│  E1局 0本場 | 残り:70 | ドラ: [4s]  | 供託: 0                  │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│                  ┌─────────────────────┐                      │
│                  │   対面 (Player 2)    │                      │
│                  │   Score: 25000       │                      │
│                  │   河: [tiles...]     │                      │
│                  │   副露: [melds...]   │                      │
│                  └─────────────────────┘                      │
│                                                                │
│  ┌──────────┐                              ┌──────────┐       │
│  │ 上家 (P3) │                              │ 下家 (P1) │       │
│  │ Score     │        Center Area          │ Score     │       │
│  │ 河        │                              │ 河        │       │
│  │ 副露      │    (future: table graphic)  │ 副露      │       │
│  └──────────┘                              └──────────┘       │
│                                                                │
│                  ┌─────────────────────┐                      │
│                  │   自家 (Player 0)    │                      │
│                  │   河: [tiles...]     │                      │
│                  │   副露: [melds...]   │                      │
│                  └─────────────────────┘                      │
│                                                                │
├──────────────────────────────────────────────────────────────┤
│  Hand Area                                                     │
│  ┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐  ┌───┐ │
│  │1m ││2m ││3m ││5p ││6p ││7p ││2s ││3s ││4s ││ E │  │ツモ│ │
│  └───┘└───┘└───┘└───┘└───┘└───┘└───┘└───┘└───┘└───┘  └───┘ │
│                                                      ↑ gap    │
│  [Action Buttons: 立直 | ツモ | ロン | 吃 | 碰 | 杠 | 跳过]   │
├──────────────────────────────────────────────────────────────┤
│  AI Coach Panel (collapsible)                                  │
│  推荐: 3m (0.89) | 向听: 1 | 候選: 3m > 8s > 2p > 1m         │
│  ▸ 詳細分析                                                    │
└──────────────────────────────────────────────────────────────┘
```

### Component Hierarchy

```
App
├── GameInfoBar          — round/wind/dora/scores/tiles remaining
├── TableArea
│   ├── OpponentArea     × 3 (top/left/right)
│   │   ├── ScoreBadge
│   │   ├── DiscardPond
│   │   └── MeldDisplay
│   └── SelfArea
│       ├── DiscardPond
│       └── MeldDisplay
├── HandArea
│   ├── TileButton       × N (clickable, highlight on hover)
│   ├── DrawTile         (separated by gap)
│   └── ActionBar        (contextual buttons)
└── CoachPanel           (collapsible bottom bar)
    ├── RecommendBadge
    ├── CandidateList
    └── DetailToggle
```

### Tile Rendering (CSS)

```css
.tile {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  width: 36px;
  height: 52px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,0.12);
  font-size: 14px;
  font-weight: 600;
  cursor: default;
  user-select: none;
}
.tile-man  { color: #c0392b; }  /* red */
.tile-pin  { color: #2980b9; }  /* blue */
.tile-sou  { color: #27ae60; }  /* green */
.tile-wind { color: #2c3e50; }  /* dark */
.tile-dragon-C { color: #c0392b; }  /* 中: red */
.tile-dragon-F { color: #27ae60; }  /* 發: green */
.tile-dragon-P { color: #7f8c8d; }  /* 白: gray */

.tile-red { border-color: #e74c3c; background: #fff5f5; }
.tile-clickable:hover { background: #e8f4fd; transform: translateY(-4px); }
.tile-recommended { box-shadow: 0 0 0 2px #f39c12; }  /* coach highlight */

.tile-back {
  background: #1a5276;
  border-color: #154360;
}
```

Tile content layout (two lines inside the div):
```
┌─────┐
│  1  │  ← number (or kanji for honors)
│  万  │  ← suit label
└─────┘
```

### Color Palette (Minimal)

```
Background:  #f5f5f0  (warm off-white)
Table area:  #e8e4df  (subtle warm gray)
Card/Panel:  #ffffff
Text:        #2c3e50
Accent:      #3498db  (buttons, links)
Success:     #27ae60  (win indicator)
Danger:      #e74c3c  (deal-in indicator)
Coach:       #f39c12  (recommendation highlight)
Riichi:      #f1c40f  (yellow lightning)
```

### Interaction Flow

1. **Page load** → "New Game" button → sends `{"type": "new_game"}`
2. **Round starts** → server pushes `game_info` + `game_event` (start_round)
3. **AI turns** → server pushes `ai_thinking` → game events stream in → tiles appear in ponds
4. **Player turn** → server pushes `action_required` + `coach`
   - Hand tiles become clickable
   - Action buttons appear based on available actions
   - Coach panel shows recommendation (highlighted tile has golden border)
5. **Player clicks tile** → sends `{"type":"action","action_type":"discard","tile":"3m"}`
6. **Special actions** → player clicks button (riichi/tsumo/ron/chi/pon/kan/skip)
7. **Round end** → modal/overlay shows result (yaku, han/fu, score changes)
8. **Game end** → final standings overlay

### AI Thinking State

When Mortal is processing (~2s per AI turn):
- Small spinner + "AI 思考中..." text in center area
- Smooth, non-blocking (WebSocket stays responsive)

## File Structure

```
riichi-trainer/
├── backend/
│   ├── server.py          # FastAPI app, WebSocket handler, static file serving
│   ├── web_agent.py       # WebAgent (threading.Event bridge)
│   └── game_session.py    # Game lifecycle: new_game, engine thread management
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── hooks/
│       │   └── useGameSocket.ts    # WebSocket connection + message handling
│       ├── components/
│       │   ├── GameInfoBar.tsx
│       │   ├── TableArea.tsx
│       │   ├── OpponentArea.tsx
│       │   ├── DiscardPond.tsx
│       │   ├── MeldDisplay.tsx
│       │   ├── HandArea.tsx
│       │   ├── Tile.tsx            # Core tile component (CSS rendering)
│       │   ├── ActionBar.tsx
│       │   ├── CoachPanel.tsx
│       │   ├── RoundResultModal.tsx
│       │   └── GameEndOverlay.tsx
│       ├── types/
│       │   └── game.ts            # TypeScript types matching WS protocol
│       └── styles/
│           └── tiles.css
├── game/       # existing, unchanged
├── ai/         # existing, unchanged
└── model/      # existing, unchanged
```

## MVP Scope

### Included
- Complete game play (full hanchan)
- Clickable hand tiles for discard
- All call actions (chi/pon/kan/riichi/tsumo/ron)
- 4-player discard ponds + melds display
- Score tracking + game info bar
- AI coach panel (recommended tile + candidate ranking + shanten)
- Round result display (yaku/han/fu)
- Game end standings

### NOT Included (v2+)
- Sound effects / animations
- Mobile responsive layout
- Game replay / review mode
- Statistics dashboard
- Tile image assets (CSS-only in v1)

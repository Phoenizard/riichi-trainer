# Riichi Mahjong AI Trainer — Claude Code Handoff

## Project Overview

A single-player Japanese Riichi Mahjong training app. Human plays against 3 AI opponents (Mortal) with a real-time AI coach analyzing every decision.

**Core Architecture**: Game Engine (Python) + Mortal AI (local libriichi + PyTorch) + Web UI (FastAPI + React/TypeScript)

**Target User**: The developer themselves (personal training tool)

**Current Phase**: Web UI fully playable with Mortal AI, real-time coaching, tile efficiency analysis, database logging, and per-round AI agreement tracking.

---

## Repository Layout

```
riichi-trainer/
├── start_web.py              # Web UI entry point: `python start_web.py` → http://localhost:8000
├── main.py                   # Terminal UI entry point (legacy)
├── terminal_ui.py            # Terminal interactive UI
├── game/
│   ├── tiles.py              # Tile notation, sorting, dora calculation, tiles_to_136
│   ├── engine.py             # Full game engine: dealing, calls, scoring, game flow
│   └── efficiency.py         # Tile efficiency calculation (shanten-based)
├── ai/
│   ├── mock_agent.py         # Heuristic AI fallback
│   ├── mortal_agent.py       # Triple-mode Mortal: libriichi / MJAPI / Docker
│   ├── mortal_engine.py      # PyTorch model loading, MortalEngine wrapper
│   └── mortal_model.py       # Neural network architecture (Brain + DQN)
├── backend/
│   ├── server.py             # FastAPI + WebSocket server
│   ├── web_agent.py          # Bridge async WS ↔ sync engine (threading.Event + Queue)
│   ├── game_session.py       # Engine thread lifecycle, AI agent management
│   └── db.py                 # SQLite game/round/decision logging (GameLogger)
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Main app component, state management
│   │   ├── hooks/useGameSocket.ts  # WebSocket + useReducer state
│   │   ├── components/       # Tile, HandArea, ActionBar, CoachPanel, OpponentArea,
│   │   │                     # TableArea, MeldDisplay, DiscardPond, RoundResultModal,
│   │   │                     # GameInfoBar, GameEndOverlay, EfficiencyPanel
│   │   ├── types/game.ts     # TypeScript types matching WS protocol
│   │   └── styles/tiles.css  # All CSS (pure CSS tiles, no images)
│   └── dist/                 # Production build (served by FastAPI)
├── data/                     # SQLite databases (gitignored)
├── model/                    # Mortal v4 weights (~91MB each)
├── tmp/Mortal/               # Mortal source (for libriichi compilation)
├── tests/
│   ├── test_efficiency.py    # Tile efficiency unit tests
│   └── test_db.py            # Database logging unit tests
└── docs/WEB_UI_SPEC.md       # Web UI design spec
```

---

## What's Done

### 1. Game Engine (`game/engine.py`) ✅
- Complete 4-player East-South game with all rules
- Chi/Pon/Kan, Riichi, Tsumo/Ron, Furiten, exhaustive draw
- Proper han/fu scoring via `mahjong` library (HandCalculator)
- Meld-aware win detection (closed mentsu count = 4 - open melds)
- Correct call priority: ron > pon/kan > chi, all options presented per player at once
- Riichi auto-discard with delay (shows drawn tile before tsumogiri)
- Tsumo with skip option (player can decline and discard instead)
- Stress tested: 20+ full games without errors

### 2. Mortal AI Integration ✅
- **Local libriichi** compiled from Rust source (macOS ARM)
- `libriichi.mjai.Bot(engine, seat)` → `bot.react(json_str)` for inference
- 3 AI opponents (seats 1-3) + 1 coach shadow (seat 0)
- Auto-detect: falls back to MockAgent if model/libriichi unavailable
- MortalAnalysis: q_values, shanten, candidate rankings, recommended_action/tile

### 3. Web UI ✅
- **Backend**: FastAPI WebSocket server, one session per connection
  - WebAgent bridges async WS ↔ sync GameEngine via threading primitives
  - AI action delay (1.2s) for immersive pacing
  - Active turn tracking sent to frontend
- **Frontend**: React + TypeScript + Vite, pure CSS tile rendering
  - Full game flow: lobby → playing → round result → game end
  - Hand tiles with click-to-discard, action bar (pon/chi/kan/riichi/tsumo/ron/skip)
  - AI Coach panel: recommended action/tile, candidate bar chart, shanten, show/hide toggle
  - Opponent areas with peek-at-hand toggle, active turn highlighting (blue border)
  - Round result modal with winning hand display, Chinese yaku names
  - Draw result shows tenpai players' hands
  - Meld display: called tile sideways, positioned by source direction (上/対/下)
  - Red five: corner dot marker (not border), avoids conflict with recommendation highlight
  - Coach riichi recommendation shows "立直 → [tile]"
  - Chinese wind labels (東南西北) throughout UI

### 4. Tile Efficiency Panel ✅
- Collapsible panel below hand area
- Shows for each possible discard: 进张 tiles, 总进张 count, 剩余 (visible-adjusted)
- Best row highlighted, low remaining in orange
- Shanten badge in header
- localStorage persistence for collapsed state

### 5. Database Logging ✅
- SQLite with three tables: games, rounds, decisions
- Records every decision point: player action vs AI recommendation
- Match detection (agreement rate) per round
- Round result modal shows "AI 一致率: M/N (X%)"
- DB file at `data/games.db` (gitignored)

### 6. Terminal UI (`terminal_ui.py`) ✅
- Full interactive play, Chinese labels, AI action delays
- Preserved as fallback, not actively developed

---

## What's NOT Done (Remaining Tasks)

### TODOs (documented, not yet implementing)

1. **"为什么不推荐打XXX" 对话框** — Ask about specific non-recommended tiles. Needs LLM or Q-value explanation.
2. **每局结束复盘页面** — Per-round review (not per-hanchan). Show key decision points + AI vs user comparison. Database infrastructure ready.
3. **AI 教学指导** — Mortal only outputs Q-values, not explanations. Need LLM layer (Claude) to translate decisions into teaching. Related to #1.

### MJAPI (deprioritized)
- Community URLs are ephemeral. Local inference is primary path.
- MJAPI client code retained in `mortal_agent.py` if needed.

---

## Key Technical Decisions

### Architecture
- **Threading model**: GameEngine runs in separate thread (sync, blocking). WebAgent bridges via `threading.Event` + `queue.Queue` to async FastAPI WebSocket.
- **Coach timing**: MortalAgent shadow at seat 0 receives `on_event()` calls. Analysis computed during `on_event()` (Mortal runs inference internally). `choose_action()` reads `get_analysis()` — zero extra latency.
- **Round result blocking**: `_round_continue = threading.Event()` blocks engine thread until frontend sends `continue_round`.
- **Call priority**: All options (ron/pon/chi/skip) presented to each player in a single prompt. Ron decisions resolve before pon/chi across players.

### Tile Notation
Internal: `"1m"`, `"0m"` (red five). Mortal mjai: `"5mr"`. Translation in `mortal_agent.py`.

### Tile-to-136 Format
Regular 5s always start from index 1 (index 0 reserved for aka dora in mahjong library). Red fives use index 0.

### Agent Protocol
```python
class Agent(Protocol):
    def choose_action(self, player_id, game_state, available_actions) -> Action: ...
    def on_event(self, event: dict) -> None: ...
```

---

## Quick Start

```bash
cd riichi-trainer
conda activate reach

# Web UI (primary)
python start_web.py          # → http://localhost:8000

# Terminal UI (legacy)
python main.py

# Run tests
conda run -n reach python -m pytest tests/ -v

# Automated engine test
python -c "
from game.engine import GameEngine
from ai.mock_agent import MockAgent
agents = [MockAgent(f'P{i}') for i in range(4)]
engine = GameEngine(agents)
for r in range(5):
    state = engine.play_round()
    print(f'Round {r+1}: {state.result.value}, scores={engine.game_scores}')
"
```

---

## Dependencies

```
Python 3.9+, conda env "reach"
mahjong==1.4.0       # Hand evaluation, scoring
torch                # Mortal model inference
fastapi + uvicorn    # Web backend
libriichi            # Compiled from tmp/Mortal/ (Rust → .so)
requests             # MJAPI client (optional)
pytest               # Testing
```

Frontend: Node.js, React 19, TypeScript, Vite.

# Riichi Mahjong AI Trainer — Claude Code Handoff

## Project Overview

A single-player Japanese Riichi Mahjong training app. Human plays against 3 AI opponents with a real-time AI coach analyzing every decision.

**Core Architecture**: Game Engine (Python) + Mortal AI (decision engine via mjai protocol) + LLM (natural language coaching explanations)

**Target User**: The developer themselves (personal training tool)

**Current Phase**: Terminal-playable prototype with mock AI. Mortal integration interface written, pending API connectivity test.

---

## Repository Layout

```
riichi-trainer/
├── main.py                 # Entry point: `python3 main.py`
├── terminal_ui.py          # Terminal interactive UI (305 lines)
│                            Human player at seat 0, shows hand/discards/AI recommendations
├── game/
│   ├── tiles.py            # Tile definitions, sorting, display, dora calculation (196 lines)
│   └── engine.py           # Full game engine: dealing, draw-discard, chi/pon/kan, scoring (971 lines)
├── ai/
│   ├── mock_agent.py       # Heuristic AI opponent placeholder (122 lines)
│   └── mortal_agent.py     # Dual-mode Mortal interface: MJAPI online + Docker local (474 lines)
├── test_mjapi.py           # MJAPI connectivity test script
└── riichi-trainer-architecture.md  # Full architecture design doc
```

Also in the workspace:
- `MahjongCopilot/` — Cloned reference implementation of Mortal integration (read-only reference)
- `model/` — **Mortal v4 model weights (AVAILABLE)**:
  - `model_v4_20240308_best_min.pth` (91MB) — best checkpoint
  - `model_v4_20240308_mortal_min.pth` (91MB) — mortal checkpoint
  - Config: `version=4, conv_channels=256, num_blocks=54`
  - ~24M parameters (Brain: 23.7M + DQN: 48K)
  - Load with: `torch.load(path, map_location='cpu', weights_only=False)`
  - Keys: `state['config']`, `state['mortal']` (Brain weights), `state['current_dqn']` (DQN weights)
  - Reference loading code: `../MahjongCopilot/bot/local/engine.py` → `get_engine()`

---

## What's Done

### 1. Game Engine (`game/engine.py`)
- Complete 4-player game state management
- 136-tile wall construction with red fives (赤ドラ)
- Draw-discard loop with proper turn rotation
- Chi (チー) / Pon (ポン) / Kan (カン) call detection and handling
- Riichi (リーチ) declaration
- Tsumo (ツモ) and Ron (ロン) win detection
- Regular hand patterns + seven pairs (七対子)
- Furiten (振聴) checking
- Exhaustive draw (流局) with tenpai payments
- East-South game flow, renchan (連荘), honba (本場)
- Game end conditions (negative score, South 4 completion)
- **Stress tested**: 20 full games (258 rounds) completed without errors

### 2. Tile System (`game/tiles.py`)
- mjai-compatible notation (1m-9m, 1p-9p, 1s-9s, E/S/W/N, P/F/C, 0m/0p/0s for red fives)
- Sorting, display (kanji + unicode), dora indicator → dora tile calculation

### 3. AI Agent Interface (`ai/mortal_agent.py`)
Dual-mode agent supporting:
- **MJAPI (online)**: `MortalAgent.create_mjapi(player_id, api_url, model="baseline")`
  - Full REST client: register → login → start_bot → act/batch → stop_bot
  - API protocol reverse-engineered from MahjongCopilot source code
- **Docker (local)**: `MortalAgent.create_docker(player_id, model_dir)`
  - stdin/stdout JSON over mjai protocol
- **Analysis parsing**: `MortalAnalysis` dataclass extracts q_values, shanten, candidate tile rankings
- Unified `choose_action()` / `on_event()` interface matches the GameEngine `Agent` protocol

### 4. Terminal UI (`terminal_ui.py`)
- Full interactive play: shows hand (indexed), discards, scores, dora, AI actions
- Special action menu (tsumo/ron/riichi/chi/pon/kan)
- Round results display

### 5. Architecture Document
- Complete system design at `riichi-trainer-architecture.md`
- Covers: all components, data flow, DB schema (SQLite), API design (FastAPI+WebSocket), project structure, 5-phase roadmap

---

## What's NOT Done (Remaining Tasks)

### Priority 1: Mortal AI Connection

**MJAPI Status (2026-03-18)**: Both tested URLs have FAILED:
- `https://cdt-authentication-consultation-significance.trycloudflare.com` → DNS resolution failed (temporary Cloudflare tunnel expired)
- `https://mjai.7xcnnw11phu.eu.org` → Also unreachable (proxy blocked / domain down)

The MJAPI is a community-run temporary service with no uptime guarantee. URLs rotate frequently.

**However, local model weights are now available** in `model/` directory (v4, obtained from MahjongCopilot community). This makes MJAPI non-critical — **local inference is the primary path**.

**Next steps**:
1. **PRIMARY**: Build local Mortal inference using `libriichi` + PyTorch (model files in `model/`)
   - Reference code: `../MahjongCopilot/bot/local/engine.py` and `model.py`
   - Requires: compiled `libriichi.so` (Rust → Python binding) — build from Mortal source or extract from MahjongCopilot
   - The `libriichi.pyd` in `../MahjongCopilot/libriichi/` is Windows-only; need to compile for current platform
   - `libriichi` provides: `libriichi.mjai.Bot(engine, seat)` + `bot.react(json_str)` — handles all mjai state tracking internally
2. **FALLBACK**: If `libriichi` compilation is difficult, use Docker mode (`ai/mortal_agent.py` DockerMortalClient)
3. **OPTIONAL**: Find working MJAPI URL as secondary online option
- [ ] **Wire MortalAgent into GameEngine**: Replace MockAgent with MortalAgent for:
  - 3 AI opponents (seats 1-3)
  - 1 coach instance on seat 0 (analyzes human's position)
- [ ] **If MJAPI unavailable**: Set up AutoDL training (see Training Plan section below)

### Priority 2: Scoring Integration
- [ ] Replace simplified fixed-mangan scoring with proper han/fu calculation
  - Library: `mahjong` (PyPI, already installed)
  - Need to: convert tile notation to library's 136-format, call `HandCalculator`
  - Key: `game/tiles.py` has `tiles_to_136()` helper already written

### Priority 3: Coach Display
- [ ] Show Mortal's recommended discard + candidate ranking in terminal UI
- [ ] Add "Why?" command that formats analysis for display (later: LLM explanation)

### Priority 4: Stats & Logging (SQLite)
- [ ] Implement DB schema from architecture doc
- [ ] Log every decision point: human choice vs AI recommendation
- [ ] Track: AI agreement rate, win rate, deal-in rate, shanten efficiency

### Priority 5: Web UI (Future)
- [ ] FastAPI + WebSocket backend
- [ ] React frontend with mahjong table
- [ ] Deferred until terminal version is feature-complete

---

## Key Technical Decisions

### Tile Notation
Uses mjai protocol format throughout: `"1m"`, `"5mr"` (red five in mjai) = `"0m"` (our internal). Red fives stored as `"0m"/"0p"/"0s"`.

### Agent Protocol
```python
class Agent(Protocol):
    def choose_action(self, player_id, game_state, available_actions) -> Action: ...
    def on_event(self, event: dict) -> None: ...
```
All agents (HumanAgent, MockAgent, MortalAgent) implement this.

### mjai Protocol Key Points (from Mortal docs)
- Player ID: East at E1 = 0, shimocha(right) = 1, toimen(across) = 2, kamicha(left) = 3
- Other players' tsumo tiles shown as `"?"`
- `start_kyoku.tehais`: 4 arrays, own tiles visible, others all `"?"`
- Mortal response includes `meta.q_values` (34 floats for discard candidates) + `shanten`
- `meta.mask_bits`: bitmask of legal actions
- Red five notation: `"5mr"` / `"5pr"` / `"5sr"` in mjai (we use `"0m"/"0p"/"0s"` internally, need translation layer)

### Model File Format (for local training)
PyTorch state dict containing:
- `state['config']['control']['version']` (1-4, latest is 4)
- `state['config']['resnet']['conv_channels']` / `num_blocks`
- `state['mortal']` → Brain (ResNet encoder) weights
- `state['current_dqn']` → DQN (Dueling DQN) weights
Model architecture: ResNet with CBAM attention → 1024-dim features → Dueling DQN (V + A heads)

---

## MJAPI Protocol Reference

```
POST /user/register     {"name": str} → {"secret": str}
POST /user/login        {"name": str, "secret": str} → {"id": token}
GET  /mjai/list         → {"models": ["baseline", "aggressive", ...]}
GET  /mjai/usage        → {"used": int}
POST /mjai/start        {"id": seat, "bound": 256, "model": str}
POST /mjai/act          {"seq": int, "data": mjai_event} → {"act": mjai_reaction}
POST /mjai/batch        [{"seq": int, "data": mjai_event}, ...] → {"act": last_reaction}
POST /mjai/stop
POST /user/logout
```
Auth: Bearer token in header after login.

---

## Training Plan (if MJAPI unavailable)

### On AutoDL (RTX 4090, ~¥2/hr)

```bash
# 1. Environment
git clone https://github.com/Equim-chan/Mortal.git && cd Mortal
conda env create -f environment.yml && conda activate mortal
pip install torch  # CUDA version
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo build -p libriichi --lib --release
cp target/release/libriichi.so mortal/libriichi.so

# 2. Data: Tenhou phoenix-table logs → mjai format
# Use: github.com/NikkeTryHard/tenhou-to-mjai

# 3. Offline RL training (behavior cloning from human games)
# 4. Online RL training (self-play refinement)
```

Estimated: 10-21 days, ¥500-1050 total.

---

## Dependencies

```
Python 3.9+
mahjong==1.4.0   # PyPI (installed) — hand evaluation, shanten, scoring
requests          # For MJAPI client
torch             # For local model inference (optional, only if running locally)
```

For Docker-based Mortal: `docker` installed, Mortal image built.

---

## Quick Start Commands

```bash
cd riichi-trainer

# Play with mock AI (works now)
python3 main.py

# Test MJAPI connectivity (edit MJAPI_URLS in script first)
python3 test_mjapi.py

# Run automated test (all AI, no human)
python3 -c "
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

## Reference Code Locations (in MahjongCopilot/)

| What | File |
|------|------|
| Model loading & inference | `bot/local/engine.py` → `get_engine()` |
| Neural network architecture | `bot/local/model.py` → Brain, DQN, ResNet |
| MJAPI REST client | `bot/mjapi/mjapi.py` |
| MJAPI bot wrapper | `bot/mjapi/bot_mjapi.py` |
| mjai Bot (libriichi binding) | `bot/bot.py` → `BotMjai.react()` |
| libriichi compiled lib | `libriichi/libriichi.pyd` (Windows) |
| Default MJAPI URL | `common/settings.py` line 44 |

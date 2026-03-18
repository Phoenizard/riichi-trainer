# Riichi Mahjong AI Training App — System Architecture

## 1. Overview

A single-player web application for practicing Japanese Riichi Mahjong against AI opponents with real-time AI coaching. The system combines Mortal (deep RL mahjong AI) for game decisions with an LLM layer for natural language coaching.

```
┌──────────────────────────────────────────────────────┐
│                  Web Frontend (React)                  │
│                                                        │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Mahjong  │  │  AI Coach    │  │  Stats          │  │
│  │ Table UI │  │  Panel       │  │  Dashboard      │  │
│  └────┬─────┘  └──────┬───────┘  └───────┬────────┘  │
│       │               │                  │            │
└───────┼───────────────┼──────────────────┼────────────┘
        │               │                  │
        │          WebSocket            REST API
        │               │                  │
┌───────┼───────────────┼──────────────────┼────────────┐
│       │        Python Backend (FastAPI)   │            │
│       │               │                  │            │
│  ┌────┴───────────────┴──────┐   ┌──────┴────────┐   │
│  │     Game Controller       │   │  Stats API    │   │
│  │  (WebSocket session mgr)  │   │  (REST CRUD)  │   │
│  └────┬──────────┬───────────┘   └──────┬────────┘   │
│       │          │                      │            │
│  ┌────┴────┐ ┌───┴──────────┐  ┌───────┴────────┐   │
│  │  Game   │ │  AI Service  │  │   Database     │   │
│  │  Engine │ │              │  │   (SQLite)     │   │
│  │         │ │ ┌──────────┐ │  │                │   │
│  │ - Deal  │ │ │ Mortal   │ │  │ - game_logs   │   │
│  │ - Draw  │ │ │ ×4 inst  │ │  │ - decisions   │   │
│  │ - Call  │ │ │ (mjai)   │ │  │ - player_stats│   │
│  │ - Score │ │ └──────────┘ │  │ - hand_records│   │
│  │ - Rules │ │ ┌──────────┐ │  │                │   │
│  │         │ │ │ LLM API  │ │  └────────────────┘   │
│  │         │ │ │ (Claude)  │ │                       │
│  │         │ │ └──────────┘ │                       │
│  └─────────┘ └──────────────┘                       │
└──────────────────────────────────────────────────────┘
```

## 2. Core Components

### 2.1 Game Engine (Python)

The game engine manages the complete mahjong game state and rules. It does NOT rely on Mortal for game simulation — Mortal is only used for AI decisions.

**Responsibilities:**
- Tile wall generation & shuffling (136 tiles)
- Dealing (13 tiles × 4 + 1 for East)
- Dead wall & dora indicator management
- Turn loop: draw → (tsumo check) → discard → (call check) → next
- Call validation: chi / pon / kan / ron
- Riichi declaration handling
- Scoring calculation (han + fu → points)
- Exhaustive draw (ryuukyoku) handling
- Full game flow: East/South rounds, renchan, placement

**Key Data Structures:**

```python
@dataclass
class GameState:
    round_wind: str          # "E" | "S"
    round_number: int        # 0-3
    honba: int               # repeat count
    riichi_sticks: int
    scores: list[int]        # 4 players' scores
    dealer: int              # 0-3
    current_turn: int        # 0-3
    wall: list[str]          # remaining tiles
    dead_wall: list[str]
    dora_indicators: list[str]
    hands: list[list[str]]   # 4 hands (player 0 = human)
    melds: list[list[Meld]]  # open melds per player
    discards: list[list[str]]# discard ponds per player
    riichi_status: list[bool]
    ippatsu: list[bool]

@dataclass
class Meld:
    type: str                # "chi" | "pon" | "kan" | "ankan" | "kakan"
    tiles: list[str]
    from_player: int

# Tile notation: "1m"-"9m", "1p"-"9p", "1s"-"9s",
#                "E","S","W","N","P","F","C" (winds + dragons)
#                "0m","0p","0s" for red fives
```

**Recommended Libraries:**
- `mahjong` (PyPI): for hand evaluation, shanten calculation, scoring
- Custom game loop: handle the interactive turn-based flow
- mjai protocol adapter: translate GameState ↔ mjai JSON events

### 2.2 AI Service

#### 2.2.1 Mortal Integration (Decision Engine)

Mortal communicates via the **mjai protocol** (JSON over stdin/stdout). We run 4 Mortal instances: 3 as opponents, 1 as the "coach" analyzing the human player's seat.

**mjai Protocol Flow (simplified):**

```json
// Server → Bot: game start
{"type": "start_game", "id": 0, "names": ["player", "ai1", "ai2", "ai3"]}

// Server → Bot: round start
{"type": "start_kyoku", "bakaze": "E", "dora_marker": "3p",
 "kyoku": 1, "honba": 0, "kyotaku": 0, "oya": 0,
 "scores": [25000, 25000, 25000, 25000],
 "tehais": [["1m","3m","5m",...], ...]}

// Server → Bot: your turn to act (tsumo)
{"type": "tsumo", "actor": 0, "pai": "7p"}

// Bot → Server: decision
{"type": "dahai", "actor": 0, "pai": "1m", "tsumogiri": false}

// Server → Bot: another player discarded
{"type": "dahai", "actor": 2, "pai": "5s", "tsumogiri": true}
```

**Architecture Pattern:**

```python
class MortalAgent:
    """Wraps a Mortal subprocess communicating via mjai protocol."""

    def __init__(self, player_id: int, model_path: str):
        self.player_id = player_id
        self.process = subprocess.Popen(
            ["mortal", "--mjai", "--model", model_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE
        )

    def send_event(self, event: dict) -> None:
        """Send an mjai event to Mortal."""
        self.process.stdin.write(json.dumps(event) + "\n")
        self.process.stdin.flush()

    def get_action(self) -> dict:
        """Read Mortal's action response."""
        line = self.process.stdout.readline()
        return json.loads(line)

    def get_analysis(self) -> dict:
        """Get evaluation scores for all possible actions.
           (coach mode - returns probabilities for each discard)"""
        # Mortal can output action probabilities for analysis
        ...
```

**Coach Mode:**
The 4th Mortal instance sits on the human player's seat. When the human needs to act, we query it to get:
- Recommended action + probability
- Ranking of all candidate discards with scores
- Shanten / effective tiles info

#### 2.2.2 LLM Layer (Explanation Engine)

Called **on-demand** (user clicks "Why?") to translate Mortal's numerical output into coaching text.

**Input Template (to Claude API):**

```
You are a professional Riichi Mahjong coach.
Given the following game situation and AI analysis, explain the
recommended play in natural language.

## Current State
- Round: East 2, 0 honba
- Scores: You 28000 | Right 24000 | Across 22000 | Left 26000
- Your hand: 2m 3m 5m 6m 7m 2p 3p 5p 6p 7p 3s 4s 8s
- Draw: 4p
- Dora: 5m
- Visible discards: [...]
- Riichi: Right player is in riichi

## AI Analysis
- Top recommendation: discard 8s (score: 0.89)
- Alternative 1: discard 2m (score: 0.06)
- Alternative 2: discard 5p (score: 0.03)
- Current shanten: 1
- Effective tiles after 8s discard: 1m,4m,1p,4p,2s,5s (18 tiles)

## Instructions
Explain WHY 8s is the best discard. Consider:
1. Tile efficiency (shanten, effective tile count)
2. Hand value (potential yaku, dora usage)
3. Defense considerations (given Right's riichi)
4. Score situation context
Keep it concise (3-5 sentences). Use Japanese mahjong terminology.
```

### 2.3 API Layer (FastAPI)

```
Endpoints:

WebSocket /ws/game/{game_id}
  ├── server → client: game_state_update (every action)
  ├── server → client: ai_recommendation (when human's turn)
  ├── client → server: player_action (discard / call / riichi / tsumo)
  └── client → server: request_explanation (triggers LLM)

REST API:
  GET    /api/games                    # list past games
  GET    /api/games/{id}               # full game log
  GET    /api/games/{id}/hands/{round} # specific hand detail
  POST   /api/games/new                # start new game
  GET    /api/stats/overview           # aggregate stats
  GET    /api/stats/efficiency         # tile efficiency metrics
  GET    /api/stats/defense            # defense success rate
  GET    /api/stats/trends             # performance over time
```

### 2.4 Database Schema (SQLite)

```sql
-- Game session
CREATE TABLE games (
    id          TEXT PRIMARY KEY,
    started_at  DATETIME,
    ended_at    DATETIME,
    final_scores TEXT,        -- JSON [25000, 30000, ...]
    placement   INTEGER,      -- 1-4 (human's placement)
    total_rounds INTEGER
);

-- Each round (kyoku) within a game
CREATE TABLE rounds (
    id          TEXT PRIMARY KEY,
    game_id     TEXT REFERENCES games(id),
    round_wind  TEXT,         -- "E" | "S"
    round_num   INTEGER,      -- 1-4
    honba       INTEGER,
    result_type TEXT,         -- "tsumo" | "ron" | "draw" | "chombo"
    winner      INTEGER,      -- player seat or null
    loser       INTEGER,      -- player seat or null
    score_delta TEXT,         -- JSON
    full_log    TEXT          -- JSON: complete mjai event log
);

-- Every decision point where human acted
CREATE TABLE decisions (
    id               TEXT PRIMARY KEY,
    round_id         TEXT REFERENCES rounds(id),
    turn_number      INTEGER,
    hand             TEXT,     -- JSON: hand tiles
    draw             TEXT,     -- drawn tile
    game_context     TEXT,     -- JSON: scores, discards, dora, etc.
    player_action    TEXT,     -- what human actually did
    ai_recommendation TEXT,   -- what Mortal recommended
    ai_scores        TEXT,    -- JSON: {tile: score, ...}
    match            BOOLEAN, -- did human match AI?
    shanten_before   INTEGER,
    shanten_after    INTEGER
);

-- Aggregate stats (updated per game)
CREATE TABLE player_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_at     DATETIME,
    total_games     INTEGER,
    avg_placement   REAL,
    win_rate        REAL,     -- % of rounds won
    deal_in_rate    REAL,     -- % of rounds dealt in
    riichi_rate     REAL,
    call_rate       REAL,
    ai_agreement    REAL,     -- % matching Mortal's top choice
    avg_shanten_reduction REAL,
    tenpai_rate     REAL      -- % reaching tenpai
);
```

### 2.5 Web Frontend (React)

**Core Views:**

1. **Game Table** — Main play screen
   - Top-down mahjong table (4 players)
   - Player's hand at bottom (clickable to discard)
   - Discard ponds for all 4 players
   - Dora indicators display
   - Score board
   - AI recommendation overlay (highlighted tile + score bar)
   - "Explain" button → triggers LLM coaching popup

2. **Post-Hand Review** — After each round
   - Replay with step-by-step AI comparison
   - Deviation highlights (where you disagreed with AI)
   - Quick stats for the round

3. **Stats Dashboard** — Long-term tracking
   - Win rate / deal-in rate trends
   - AI agreement rate over time
   - Tile efficiency score
   - Weakness detection (e.g., "defense after riichi" accuracy)

## 3. Data Flow — One Turn Cycle

```
Human's Turn:

 ┌─────────┐  tsumo event   ┌────────────┐
 │  Game   │ ──────────────→│  Mortal    │
 │  Engine │                │  (Coach)   │
 │         │ ←──────────────│            │
 │         │  action scores │            │
 └────┬────┘                └────────────┘
      │
      │ state + AI scores
      ▼
 ┌─────────┐  recommendation ┌────────────┐
 │  API    │ ──────────────→│  Frontend  │
 │  (WS)  │                │            │
 │         │ ←──────────────│            │
 │         │  player choice │            │
 └────┬────┘                └────┬───────┘
      │                         │
      │ (if "Explain" clicked)  │
      ▼                         │
 ┌─────────┐  coaching text     │
 │  LLM   │ ──────────────────→│
 │  API   │
 └─────────┘

AI Opponent's Turn:

 ┌─────────┐  events         ┌────────────┐
 │  Game   │ ──────────────→│  Mortal    │
 │  Engine │                │  (Opponent)│
 │         │ ←──────────────│            │
 │         │  action         │            │
 └────┬────┘                └────────────┘
      │ state update
      ▼
 ┌─────────┐
 │ Frontend│ (animate opponent's action)
 └─────────┘
```

## 4. Tech Stack Summary

| Layer      | Technology           | Why                                    |
|------------|---------------------|----------------------------------------|
| Frontend   | React + TypeScript  | Component-based, rich ecosystem        |
| API        | FastAPI + WebSocket | Async Python, fast, native WS support  |
| Game Logic | Custom Python       | Full control over interactive flow     |
| Hand Eval  | `mahjong` (PyPI)    | Proven shanten/scoring library         |
| AI Engine  | Mortal (Rust+Python)| Strongest open-source riichi AI        |
| AI Coach   | Claude API          | Natural language explanation            |
| Database   | SQLite              | Zero-config, sufficient for single user|
| Deployment | Docker Compose      | One command to start everything        |

## 5. Project Structure

```
riichi-trainer/
├── backend/
│   ├── main.py              # FastAPI app entry
│   ├── game/
│   │   ├── engine.py         # Core game logic & state machine
│   │   ├── tiles.py          # Tile definitions & utils
│   │   ├── scoring.py        # Scoring wrapper (uses mahjong lib)
│   │   └── mjai_adapter.py   # GameState ↔ mjai protocol translation
│   ├── ai/
│   │   ├── mortal_agent.py   # Mortal subprocess wrapper
│   │   ├── coach.py          # Coach logic (query Mortal + format)
│   │   └── llm_explainer.py  # Claude API integration
│   ├── api/
│   │   ├── ws_handler.py     # WebSocket game session
│   │   ├── rest_routes.py    # REST endpoints (stats, history)
│   │   └── schemas.py        # Pydantic models
│   ├── db/
│   │   ├── models.py         # SQLAlchemy models
│   │   └── stats.py          # Stats computation queries
│   └── config.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── MahjongTable/  # Main game board
│   │   │   ├── Hand/          # Player hand display
│   │   │   ├── DiscardPond/   # Discard area
│   │   │   ├── AICoach/       # Recommendation overlay
│   │   │   └── StatsPanel/    # Statistics views
│   │   ├── hooks/
│   │   │   └── useGameSocket.ts
│   │   ├── store/             # Zustand / game state
│   │   └── App.tsx
│   └── package.json
├── models/                    # Mortal model weights
├── docker-compose.yml
└── README.md
```

## 6. Development Phases

### Phase 1: Core Game Loop (Week 1-2)
- [ ] Game engine: dealing, drawing, discarding (no calls)
- [ ] Mortal integration: 3 AI opponents playing
- [ ] Basic terminal UI for testing
- [ ] mjai protocol adapter

### Phase 2: Full Rules + Coach (Week 3-4)
- [ ] Chi / Pon / Kan / Ron handling
- [ ] Riichi declaration
- [ ] Complete scoring
- [ ] Coach Mortal instance for player seat
- [ ] AI recommendation output

### Phase 3: Web Frontend (Week 5-6)
- [ ] FastAPI + WebSocket server
- [ ] React mahjong table UI
- [ ] Real-time game play flow
- [ ] AI recommendation display

### Phase 4: LLM Coaching + Stats (Week 7-8)
- [ ] Claude API integration for explanations
- [ ] SQLite database & logging
- [ ] Stats dashboard
- [ ] Post-game review mode

### Phase 5: Polish & Deploy (Week 9-10)
- [ ] Docker packaging
- [ ] UI polish (animations, tile assets)
- [ ] Performance optimization
- [ ] Mobile-responsive layout (prep for future app)

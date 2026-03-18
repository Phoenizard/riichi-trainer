# Claude Code Project Instructions

## Project

Riichi Mahjong AI Training App — a terminal-based (later web-based) single-player Japanese Mahjong trainer with AI opponents and real-time AI coaching.

## Context

Read `CLAUDE_HANDOFF.md` first for complete project state, architecture, and remaining tasks.

## Collaboration Model

This project has a **split workflow**:
- **Claude Code (you)**: All code implementation, debugging, testing, feature development
- **Cowork (separate session)**: Architecture decisions, document maintenance, research, web/API analysis, planning
- **User**: Manual tasks (checking URLs in browser, community resources, AutoDL setup), final review

When you encounter decisions that need architecture input or external research (e.g., "which approach is better", "what does this API look like"), note it in code comments or ask the user — they will consult Cowork for guidance.

## Key Rules

1. **Tile notation**: Always use mjai format internally (`1m`-`9m`, `1p`-`9p`, `1s`-`9s`, `E/S/W/N`, `P/F/C`). Red fives = `0m/0p/0s`. When interfacing with Mortal mjai protocol, translate to `5mr/5pr/5sr`.
2. **Agent interface**: All AI agents must implement `choose_action(player_id, game_state, available_actions) -> Action` and `on_event(event) -> None`.
3. **Don't break the engine**: `game/engine.py` is stress-tested (20 games, 258 rounds). Run the automated test after any engine changes:
   ```python
   from game.engine import GameEngine
   from ai.mock_agent import MockAgent
   agents = [MockAgent(f'P{i}') for i in range(4)]
   engine = GameEngine(agents)
   for r in range(5):
       state = engine.play_round()
       print(f'Round {r+1}: {state.result.value}, scores={engine.game_scores}')
   ```
4. **Mortal integration**: Use `ai/mortal_agent.py` dual-mode interface. MJAPI for online, Docker for local. Don't bypass this abstraction.
5. **Reference code**: `../MahjongCopilot/bot/local/` contains the canonical Mortal model loading and inference code. Consult it for any model-related work.

## Current Priority

1. **LOCAL MORTAL INTEGRATION** — Model weights at `model/model_v4_20240308_best_min.pth` (v4, 256ch, 54 blocks, ~24M params).

   **Path A (RECOMMENDED): Compile libriichi**
   ```bash
   # Requires Rust toolchain
   # Mortal source already cloned at tmp/Mortal/ (DO NOT use /tmp/Mortal)
   cd tmp/Mortal
   cargo build -p libriichi --lib --release
   # macOS: cp target/release/libriichi.dylib <project>/libriichi.so
   # Linux: cp target/release/libriichi.so <project>/libriichi.so
   ```
   Then: `get_engine(model_file)` → `MortalEngine` → `libriichi.mjai.Bot(engine, seat)` → `bot.react(json_str)`
   Reference: `../MahjongCopilot/bot/local/engine.py` and `model.py`

   **Path B (FALLBACK): Docker mode** — if Rust compilation fails, use DockerMortalClient in `ai/mortal_agent.py`

   **DO NOT attempt Path C (pure PyTorch without libriichi)** — the observation encoder (mjai events → tensor) is embedded in libriichi's Rust code. Without it, model output will be incorrect.

   - Wire MortalAgent into GameEngine as 3 AI opponents + 1 coach
2. Proper han/fu scoring via `mahjong` library (replace simplified fixed-mangan scoring in engine)
3. Coach display (show AI recommendations + candidate ranking in terminal)
4. Stats/logging (SQLite)
5. MJAPI online mode is secondary (URLs currently down, see CLAUDE_HANDOFF.md)

## Style

- Python 3.9+, type hints, dataclasses
- Japanese mahjong terminology in comments (with English explanation)
- Concise code, no over-engineering

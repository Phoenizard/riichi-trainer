#!/usr/bin/env python3
"""
AI Spectator Mode — Watch 4 Mortal AIs play with real-time terminal display + JSON log.

Usage:
  python spectate.py                    # default 1 game
  python spectate.py --rounds 10        # play 10 rounds
  python spectate.py --speed 0.3        # faster (0.3s delay per action)
  python spectate.py --log game.jsonl   # custom log file
  python spectate.py --no-display       # log only, no terminal
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

from game.engine import GameEngine, RoundState, RoundResult, MeldType
from game.tiles import tile_to_display, dora_from_indicator, WIND_KANJI
from ai.mortal_agent import MortalAgent

MODEL_PATH = "model/model_v4_20240308_best_min.pth"
SEAT_NAMES = ["East (東)", "South (南)", "West (西)", "North (北)"]


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def display_state(state: RoundState, last_event: dict = None):
    """Render full game state to terminal."""
    clear_screen()

    # Header
    wind = WIND_KANJI.get(state.round_wind, state.round_wind)
    num = state.round_number + 1
    print(f"{'═'*60}")
    print(f"  {wind}{num}局 {state.honba}本場  供託: {state.riichi_sticks}本")
    print(f"  残り: {state.tiles_remaining}枚")
    indicators = " ".join(tile_to_display(d) for d in state.dora_indicators)
    doras = " ".join(tile_to_display(dora_from_indicator(d)) for d in state.dora_indicators)
    print(f"  ドラ表示: {indicators}  →  ドラ: {doras}")
    print(f"{'═'*60}")

    # Scores
    for i in range(4):
        marker = "▶" if i == state.current_turn else " "
        riichi = " [リーチ]" if state.players[i].is_riichi else ""
        print(f"  {marker} {SEAT_NAMES[i]:>12}: {state.scores[i]:>6}点{riichi}")
    print()

    # Hands (all visible in spectator mode)
    for i in range(4):
        ps = state.players[i]
        hand_str = " ".join(tile_to_display(t) for t in ps.hand)
        draw_str = f" + {tile_to_display(ps.draw_tile)}" if ps.draw_tile else ""
        melds_str = ""
        if ps.melds:
            meld_parts = []
            for m in ps.melds:
                tiles = " ".join(tile_to_display(t) for t in m.tiles)
                mtype = {"chi": "チー", "pon": "ポン", "ankan": "暗槓",
                         "minkan": "明槓", "kakan": "加槓"}.get(m.type.value, m.type.value)
                meld_parts.append(f"[{mtype}:{tiles}]")
            melds_str = " " + " ".join(meld_parts)
        print(f"  P{i}: {hand_str}{draw_str}{melds_str}")
    print()

    # Discard ponds
    print("─── 捨て牌 ───")
    for i in range(4):
        ps = state.players[i]
        discards = " ".join(tile_to_display(t) for t in ps.discards)
        print(f"  P{i}: {discards}")
    print()

    # Last event
    if last_event:
        etype = last_event.get("type", "")
        player = last_event.get("player", -1)
        if etype == "discard":
            tile = last_event.get("tile", "")
            tsumogiri = " (ツモ切り)" if last_event.get("tsumogiri") else ""
            print(f"  >>> P{player} 打 {tile_to_display(tile)}{tsumogiri}")
        elif etype in ("chi", "pon", "kan"):
            tile = last_event.get("tile", "")
            print(f"  >>> P{player} {etype.upper()} {tile_to_display(tile)}")
        elif etype == "reach":
            print(f"  >>> P{player} リーチ宣言!")
        elif etype == "reach_accepted":
            print(f"  >>> P{player} リーチ成立")


def display_result(state: RoundState, engine: GameEngine):
    """Show round result."""
    print(f"\n{'='*60}")
    if state.result == RoundResult.TSUMO:
        print(f"  P{state.winner} ツモ和了!")
    elif state.result == RoundResult.RON:
        print(f"  P{state.winner} ロン! (放銃: P{state.loser})")
    elif state.result == RoundResult.DRAW_NORMAL:
        print(f"  流局 (荒牌平局)")
    else:
        print(f"  {state.result.value}")

    print(f"\n  点数変動:")
    for i in range(4):
        delta = state.score_deltas[i]
        sign = "+" if delta >= 0 else ""
        print(f"    P{i}: {sign}{delta}")

    print(f"\n  現在のスコア: {engine.game_scores}")
    print(f"{'='*60}")


class SpectatorObserver:
    """Intercepts engine events for display and logging."""

    def __init__(self, display: bool = True, delay: float = 0.5, log_file=None):
        self.display = display
        self.delay = delay
        self.log_file = log_file
        self.state: RoundState = None
        self.events: list[dict] = []

    def on_event(self, event: dict):
        self.events.append(event)
        if self.log_file:
            self.log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
            self.log_file.flush()

        if not self.display:
            return

        etype = event.get("type", "")
        # Only refresh display on visible actions
        if etype in ("discard", "chi", "pon", "kan", "reach", "reach_accepted",
                      "tsumo", "ron", "ryukyoku"):
            if self.state:
                display_state(self.state, event)
                time.sleep(self.delay)


def run_spectate(rounds: int = 0, speed: float = 0.5,
                 log_path: str = None, display: bool = True):
    """Run AI spectator game."""
    # Setup log
    log_file = None
    if log_path:
        log_file = open(log_path, "w")
        log_file.write(json.dumps({"type": "game_start",
                                    "timestamp": datetime.now().isoformat(),
                                    "model": MODEL_PATH}) + "\n")

    # Create agents
    print(f"Loading Mortal model... ", end="", flush=True)
    agents = [MortalAgent.create_libriichi(i, MODEL_PATH) for i in range(4)]
    print("OK")

    # Setup observer
    observer = SpectatorObserver(display=display, delay=speed, log_file=log_file)

    # Patch engine to feed events to observer
    engine = GameEngine(agents)
    orig_log_event = engine._log_event

    def patched_log_event(event):
        orig_log_event(event)
        observer.on_event(event)

    engine._log_event = patched_log_event

    # Play
    round_num = 0
    try:
        if rounds > 0:
            # Play fixed number of rounds
            for r in range(rounds):
                state = engine.play_round()
                observer.state = state
                round_num = r + 1
                if display:
                    display_result(state, engine)
                    if r < rounds - 1:
                        input("  Enterで次の局...")
                else:
                    print(f"Round {round_num}: {state.result.value}, "
                          f"scores={engine.game_scores}")

                if log_file:
                    log_file.write(json.dumps({
                        "type": "round_result",
                        "round": round_num,
                        "result": state.result.value,
                        "scores": engine.game_scores,
                        "deltas": state.score_deltas,
                    }, ensure_ascii=False) + "\n")
        else:
            # Play full game (hanchan)
            while True:
                # Store state reference for display
                orig_init = engine._init_round
                def patched_init():
                    s = orig_init()
                    observer.state = s
                    return s
                engine._init_round = patched_init

                state = engine.play_round()
                round_num += 1
                if display:
                    display_result(state, engine)
                    input("  Enterで次の局...")
                else:
                    print(f"Round {round_num}: {state.result.value}, "
                          f"scores={engine.game_scores}")

                if log_file:
                    log_file.write(json.dumps({
                        "type": "round_result",
                        "round": round_num,
                        "result": state.result.value,
                        "scores": engine.game_scores,
                        "deltas": state.score_deltas,
                    }, ensure_ascii=False) + "\n")

                if engine._should_end_game(state):
                    break

    except KeyboardInterrupt:
        print("\n\n中断")

    # Final scores
    if display:
        print(f"\n{'═'*60}")
        print(f"  最終スコア ({round_num}局)")
        ranked = sorted(range(4), key=lambda i: engine.game_scores[i], reverse=True)
        for rank, i in enumerate(ranked, 1):
            print(f"    {rank}位: P{i} {SEAT_NAMES[i]} — {engine.game_scores[i]}点")
        print(f"{'═'*60}")

    if log_file:
        log_file.write(json.dumps({
            "type": "game_end",
            "total_rounds": round_num,
            "final_scores": engine.game_scores,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False) + "\n")
        log_file.close()
        print(f"\nLog saved: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="AI Spectator Mode")
    parser.add_argument("--rounds", type=int, default=0,
                        help="Number of rounds (0 = full game)")
    parser.add_argument("--speed", type=float, default=0.5,
                        help="Delay per action in seconds (default 0.5)")
    parser.add_argument("--log", type=str, default=None,
                        help="Log file path (JSONL format)")
    parser.add_argument("--no-display", action="store_true",
                        help="Disable terminal display (log only)")
    args = parser.parse_args()

    # Default log file if not specified
    log_path = args.log
    if log_path is None:
        log_path = f"logs/game_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        os.makedirs("logs", exist_ok=True)

    run_spectate(
        rounds=args.rounds,
        speed=args.speed,
        log_path=log_path,
        display=not args.no_display,
    )


if __name__ == "__main__":
    main()

"""
Terminal-based UI for playing Riichi Mahjong.
Human player sits at seat 0, AI opponents at seats 1-3.
"""

from __future__ import annotations
import os
import sys

from game.engine import (
    GameEngine, Action, ActionType, RoundState, PlayerState, RoundResult,
    MeldType,
)
from game.tiles import (
    sort_tiles, tile_to_display, hand_to_display, normalize, is_red,
    WIND_KANJI, WIND_NAMES, dora_from_indicator,
)
from ai.mock_agent import MockAgent

# Try to load MortalAgent for AI opponents
_USE_MORTAL = False
_MODEL_PATH = "model/model_v4_20240308_best_min.pth"
try:
    import os
    if os.path.exists(_MODEL_PATH):
        from ai.mortal_agent import MortalAgent
        import libriichi  # noqa: F401
        _USE_MORTAL = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

SEAT_NAMES = ["You (自家)", "Right (下家)", "Across (対面)", "Left (上家)"]


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(state: RoundState):
    """Print round info header."""
    wind = WIND_KANJI.get(state.round_wind, state.round_wind)
    num = state.round_number + 1
    print(f"{'='*60}")
    print(f"  {wind}{num}局 {state.honba}本場  供託リーチ棒: {state.riichi_sticks}")
    print(f"  残り: {state.tiles_remaining}枚")
    print(f"  ドラ表示: {' '.join(tile_to_display(d) for d in state.dora_indicators)}")
    doras = [dora_from_indicator(d) for d in state.dora_indicators]
    print(f"  ドラ:     {' '.join(tile_to_display(d) for d in doras)}")
    print(f"{'='*60}")


def print_scores(state: RoundState):
    """Print all player scores."""
    for i in range(4):
        marker = "◀" if i == state.current_turn else " "
        riichi = " [リーチ]" if state.players[i].is_riichi else ""
        print(f"  {marker} {SEAT_NAMES[i]}: {state.scores[i]:>6}点{riichi}")
    print()


def print_discards(state: RoundState):
    """Print discard ponds for all players."""
    print("─── 捨て牌 ───")
    for i in range(4):
        ps = state.players[i]
        discards_str = " ".join(tile_to_display(t) for t in ps.discards)
        label = SEAT_NAMES[i][:10]
        print(f"  {label:>10}: {discards_str}")
    print()


def print_melds(ps: PlayerState, label: str = ""):
    """Print open melds."""
    if not ps.melds:
        return
    meld_strs = []
    for m in ps.melds:
        tiles = " ".join(tile_to_display(t) for t in m.tiles)
        meld_type = {"chi": "チー", "pon": "ポン", "ankan": "暗槓",
                     "minkan": "明槓", "kakan": "加槓"}.get(m.type.value, m.type.value)
        meld_strs.append(f"[{meld_type}: {tiles}]")
    print(f"  {label}副露: {' '.join(meld_strs)}")


def print_hand(ps: PlayerState, show_index: bool = True):
    """Print the human player's hand."""
    tiles = sort_tiles(ps.hand)
    print("─── 手牌 ───")

    # Index row
    if show_index:
        idx_row = "  "
        for i in range(len(tiles)):
            idx_row += f" {i:<4}"
        print(idx_row)

    # Tile row
    tile_row = "  " + " ".join(f"{tile_to_display(t)}" for t in tiles)
    print(tile_row)

    # Draw tile
    if ps.draw_tile:
        draw_idx = len(tiles)
        print(f"  ツモ [{draw_idx}]: {tile_to_display(ps.draw_tile)}")

    print_melds(ps, "自家")
    print()


# ---------------------------------------------------------------------------
# Human agent
# ---------------------------------------------------------------------------

class HumanAgent:
    """Terminal-based human player."""

    def choose_action(
        self,
        player_id: int,
        game_state: RoundState,
        available_actions: list[Action],
    ) -> Action:
        """Prompt the human to choose an action."""
        ps = game_state.players[player_id]

        # Show game state
        clear_screen()
        print_header(game_state)
        print_scores(game_state)
        print_discards(game_state)
        print_hand(ps)

        # Group actions by type
        skip_action = next((a for a in available_actions if a.type == ActionType.SKIP), None)
        special_actions = [a for a in available_actions
                          if a.type not in (ActionType.DISCARD, ActionType.SKIP)]
        discard_actions = [a for a in available_actions if a.type == ActionType.DISCARD]
        # Always show skip as the last special action when there are call options
        if skip_action and special_actions:
            special_actions.append(skip_action)

        # Show special actions first
        if special_actions:
            print("─── 特殊行動 ───")
            for i, a in enumerate(special_actions):
                desc = self._describe_action(a, ps)
                print(f"  [{chr(ord('a') + i)}] {desc}")
            print()

        # Show discard prompt
        if discard_actions:
            tiles = sort_tiles(ps.hand)
            all_tiles = tiles + ([ps.draw_tile] if ps.draw_tile else [])
            print(f"打牌を選択 (0-{len(all_tiles)-1})")
            if special_actions:
                letters = "".join(chr(ord('a') + i) for i in range(len(special_actions)))
                print(f"特殊行動: {letters}")

        while True:
            try:
                raw = input("\n> ").strip().lower()
                if not raw:
                    continue

                # Special action by letter
                if raw.isalpha() and len(raw) == 1:
                    idx = ord(raw) - ord('a')
                    if 0 <= idx < len(special_actions):
                        return special_actions[idx]
                    print("無効な選択です")
                    continue

                # Discard by index
                if raw.isdigit():
                    idx = int(raw)
                    tiles = sort_tiles(ps.hand)
                    all_tiles = tiles + ([ps.draw_tile] if ps.draw_tile else [])

                    if 0 <= idx < len(all_tiles):
                        chosen_tile = all_tiles[idx]
                        # Find matching discard action
                        for a in discard_actions:
                            if a.tile == chosen_tile:
                                return a
                            # Try normalized match
                            if normalize(a.tile) == normalize(chosen_tile):
                                return a
                        # If no exact match, create one
                        return Action(ActionType.DISCARD, player_id, tile=chosen_tile)

                    print(f"0-{len(all_tiles)-1}の範囲で入力してください")
                    continue

                print("無効な入力です")

            except (EOFError, KeyboardInterrupt):
                print("\nゲーム中断")
                sys.exit(0)

        return available_actions[0]

    def _describe_action(self, action: Action, ps: PlayerState) -> str:
        """Human-readable description of a special action."""
        if action.type == ActionType.TSUMO:
            return f"ツモ! ({tile_to_display(ps.draw_tile)}で和了)"

        if action.type == ActionType.RON:
            return f"ロン! ({tile_to_display(action.tile)}で和了)"

        if action.type == ActionType.RIICHI:
            return f"リーチ宣言 → 打 {tile_to_display(action.tile)}"

        if action.type == ActionType.PON:
            return f"ポン ({tile_to_display(action.tile)})"

        if action.type == ActionType.CHI:
            meld_str = " ".join(tile_to_display(t) for t in action.meld_tiles)
            return f"チー ({meld_str} + {tile_to_display(action.tile)})"

        if action.type == ActionType.KAN:
            return f"カン ({tile_to_display(action.tile)})"

        if action.type == ActionType.SKIP:
            return "パス (見送り)"

        return str(action.type.value)

    def on_event(self, event: dict) -> None:
        """Show game events to the player."""
        import time
        etype = event.get("type", "")
        player = event.get("player", -1)

        if etype == "discard" and player != 0:
            tile = event.get("tile", "")
            name = SEAT_NAMES[player] if 0 <= player < 4 else f"Player {player}"
            print(f"  {name} → 打 {tile_to_display(tile)}")

        elif etype == "draw" and player != 0:
            pass  # Don't show other players' draws

        elif etype in ("chi", "pon", "kan") and player != 0:
            name = SEAT_NAMES[player] if 0 <= player < 4 else f"Player {player}"
            call_name = {"chi": "チー(吃)", "pon": "ポン(碰)", "kan": "カン(杠)"}.get(etype, etype)
            tile = event.get("tile", "")
            print(f"  {name} → {call_name} {tile_to_display(tile)}")
            time.sleep(1)

        elif etype == "reach" and player != 0:
            name = SEAT_NAMES[player] if 0 <= player < 4 else f"Player {player}"
            print(f"  {name} → リーチ(立直)!")
            time.sleep(1)


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------

def print_round_result(state: RoundState):
    """Print the result of a round."""
    print("\n" + "=" * 60)
    if state.result == RoundResult.TSUMO:
        name = SEAT_NAMES[state.winner]
        print(f"  {name} ツモ和了!")
    elif state.result == RoundResult.RON:
        winner = SEAT_NAMES[state.winner]
        loser = SEAT_NAMES[state.loser]
        print(f"  {winner} ロン! (放銃: {loser})")
    elif state.result == RoundResult.DRAW_NORMAL:
        print("  流局 (荒牌平局)")
    else:
        print(f"  {state.result.value}")

    print("\n  点数変動:")
    for i in range(4):
        delta = state.score_deltas[i]
        sign = "+" if delta >= 0 else ""
        print(f"    {SEAT_NAMES[i]}: {sign}{delta}")
    print("=" * 60)
    input("\nEnterで続行...")


def run_game():
    """Run a full game in the terminal."""
    clear_screen()
    print("╔══════════════════════════════════════╗")
    print("║     立直麻雀 AI トレーナー            ║")
    print("║     Riichi Mahjong AI Trainer        ║")
    print("╚══════════════════════════════════════╝")
    print()
    print("あなた = 席0 (自家)")
    print("AI対戦相手 × 3")
    print()
    input("Enterでゲーム開始...")

    human = HumanAgent()
    if _USE_MORTAL:
        print("AI: Mortal v4 (local)")
        agents = [human,
                  MortalAgent.create_libriichi(1, _MODEL_PATH),
                  MortalAgent.create_libriichi(2, _MODEL_PATH),
                  MortalAgent.create_libriichi(3, _MODEL_PATH)]
    else:
        print("AI: MockAgent (heuristic)")
        agents = [human, MockAgent("AI-1"), MockAgent("AI-2"), MockAgent("AI-3")]

    engine = GameEngine(agents)

    try:
        final_scores = engine.play_game()
    except KeyboardInterrupt:
        print("\nゲーム中断")
        return

    # Final results
    clear_screen()
    print("╔══════════════════════════════════════╗")
    print("║           最終結果                    ║")
    print("╚══════════════════════════════════════╝")
    print()

    ranked = sorted(range(4), key=lambda i: final_scores[i], reverse=True)
    for rank, i in enumerate(ranked, 1):
        name = SEAT_NAMES[i]
        print(f"  {rank}位: {name} - {final_scores[i]}点")

    print()
    your_rank = ranked.index(0) + 1
    print(f"あなたの順位: {your_rank}位")


if __name__ == "__main__":
    run_game()

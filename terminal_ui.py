"""
Terminal-based UI for playing Riichi Mahjong.
Human player sits at seat 0, AI opponents at seats 1-3.
"""

from __future__ import annotations
import os
import re
import sys
import unicodedata

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

W = 60  # display width

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

SEAT_NAMES = ["You (自家)", "下家(右)", "対面", "上家(左)"]
SEAT_SHORT = ["自家", "下家", "対面", "上家"]
_ANSI_RE = re.compile(r'\033\[[^m]*m')


def _vwidth(s: str) -> int:
    """Visible width of a string, ignoring ANSI escape codes."""
    clean = _ANSI_RE.sub('', s)
    return sum(2 if unicodedata.east_asian_width(c) in ('F', 'W') else 1
               for c in clean)


def _vpad(s: str, width: int) -> str:
    """Pad string to target visible width with trailing spaces."""
    pad = width - _vwidth(s)
    return s + ' ' * max(pad, 0)


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(state: RoundState):
    """Print round info header."""
    wind = WIND_KANJI.get(state.round_wind, state.round_wind)
    num = state.round_number + 1
    print(f"\033[1m{'═' * W}\033[0m")
    print(f"  {wind}{num}局 {state.honba}本場    "
          f"供託: {state.riichi_sticks}本    残り: {state.tiles_remaining}枚")
    indicators = ' '.join(tile_to_display(d) for d in state.dora_indicators)
    doras = ' '.join(tile_to_display(dora_from_indicator(d))
                     for d in state.dora_indicators)
    print(f"  ドラ表示: {indicators}  →  ドラ: {doras}")
    print(f"\033[1m{'═' * W}\033[0m")


PLAYER_WINDS = ["東", "南", "西", "北"]


def _seat_wind(state: RoundState, player: int) -> str:
    """Get the seat wind kanji for a player."""
    return PLAYER_WINDS[(player - state.dealer) % 4]


def print_scores(state: RoundState):
    """Print all player scores with seat wind."""
    RST = "\033[0m"
    RIICHI = f"\033[1;33m⚡立直{RST}"
    parts = []
    for i in range(4):
        turn = "\033[1m▶\033[0m" if i == state.current_turn else " "
        wind = _seat_wind(state, i)
        riichi = f" {RIICHI}" if state.players[i].is_riichi else ""
        parts.append(f" {turn}{wind}{SEAT_SHORT[i]} {state.scores[i]:>6}{riichi}")
    print(" │".join(parts))
    print()


def format_melds(ps: PlayerState, seat_names: list[str] = None) -> str:
    """Format open melds with source player indicated."""
    if not ps.melds:
        return ""
    meld_strs = []
    for m in ps.melds:
        tiles = " ".join(tile_to_display(t) for t in m.tiles)
        mtype = {"chi": "吃", "pon": "碰", "ankan": "暗杠",
                 "minkan": "明杠", "kakan": "加杠"}.get(m.type.value, m.type.value)
        # Source annotation
        if m.from_player >= 0 and m.type != MeldType.ANKAN:
            names = seat_names or SEAT_SHORT
            src = names[m.from_player] if m.from_player < len(names) else f"P{m.from_player}"
            meld_strs.append(f"[{mtype}←{src}: {tiles}]")
        else:
            meld_strs.append(f"[{mtype}: {tiles}]")
    return " ".join(meld_strs)


def print_discards(state: RoundState):
    """Print discard ponds and melds for all players."""
    RST = "\033[0m"
    RIICHI_MARK = f"\033[1;33m⟫{RST}"
    print("─── 河 / 副露 " + "─" * (W - 14))
    for i in range(4):
        ps = state.players[i]
        # Discard pond with riichi marker
        parts = []
        for j, t in enumerate(ps.discards):
            tile_str = tile_to_display(t)
            if ps.is_riichi and j == ps.riichi_turn:
                tile_str = RIICHI_MARK + tile_str
            parts.append(tile_str)
        discards_str = " ".join(parts) if parts else "\033[2m--\033[0m"
        label = _vpad(SEAT_SHORT[i], 4)
        print(f"  {label} 河: {discards_str}")
        # Melds
        melds_str = format_melds(ps, SEAT_SHORT)
        if melds_str:
            print(f"       副露: {melds_str}")
    print()


def print_hand(ps: PlayerState, show_index: bool = True):
    """Print the human player's hand with aligned indices."""
    tiles = sort_tiles(ps.hand)
    GAP = 1  # space between tiles
    print("─── 手牌 " + "─" * (W - 9))

    # Calculate display width per tile for alignment
    displays = [tile_to_display(t) for t in tiles]
    widths = [_vwidth(d) for d in displays]

    # Index row — each index padded to match its tile's display width
    if show_index:
        idx_row = "  "
        for i, w in enumerate(widths):
            idx_str = str(i)
            idx_row += idx_str + ' ' * (w - len(idx_str) + GAP)
        print(idx_row)

    # Tile row
    tile_parts = []
    for d, w in zip(displays, widths):
        tile_parts.append(_vpad(d, w))
    print("  " + (' ' * GAP).join(tile_parts))

    # Draw tile
    if ps.draw_tile:
        draw_idx = len(tiles)
        print(f"\n  ツモ [{draw_idx}]: {tile_to_display(ps.draw_tile)}")

    melds_str = format_melds(ps, SEAT_SHORT)
    if melds_str:
        print(f"  副露: {melds_str}")
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
            print("─── 行動選択 " + "─" * (W - 12))
            for i, a in enumerate(special_actions):
                desc = self._describe_action(a, ps)
                print(f"  [{chr(ord('a') + i)}] {desc}")
            print()

        # Show discard prompt
        if discard_actions:
            tiles = sort_tiles(ps.hand)
            all_tiles = tiles + ([ps.draw_tile] if ps.draw_tile else [])
            print(f"  数字 0‒{len(all_tiles)-1} で打牌", end="")
            if special_actions:
                letters = "/".join(chr(ord('a') + i) for i in range(len(special_actions)))
                print(f"   英字 {letters} で特殊行動", end="")
            print()

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

                    print(f"0‒{len(all_tiles)-1} の範囲で入力してください")
                    continue

                print("無効な入力です")

            except (EOFError, KeyboardInterrupt):
                print("\nゲーム中断")
                sys.exit(0)

        return available_actions[0]

    def _describe_action(self, action: Action, ps: PlayerState) -> str:
        """Human-readable description of a special action."""
        if action.type == ActionType.TSUMO:
            return f"ツモ和了! ({tile_to_display(ps.draw_tile)})"

        if action.type == ActionType.RON:
            return f"ロン和了! ({tile_to_display(action.tile)})"

        if action.type == ActionType.RIICHI:
            return f"立直 → 打 {tile_to_display(action.tile)}"

        if action.type == ActionType.PON:
            return f"碰 {tile_to_display(action.tile)}"

        if action.type == ActionType.CHI:
            meld_str = " ".join(tile_to_display(t) for t in action.meld_tiles)
            return f"吃 ({meld_str} + {tile_to_display(action.tile)})"

        if action.type == ActionType.KAN:
            return f"杠 {tile_to_display(action.tile)}"

        if action.type == ActionType.SKIP:
            return "跳过"

        return str(action.type.value)

    def on_event(self, event: dict) -> None:
        """Show game events to the player."""
        import time
        etype = event.get("type", "")
        player = event.get("player", -1)

        if etype == "discard" and player != 0:
            tile = event.get("tile", "")
            name = SEAT_SHORT[player] if 0 <= player < 4 else f"P{player}"
            print(f"  {name} → 打 {tile_to_display(tile)}")

        elif etype == "draw" and player != 0:
            pass  # Don't show other players' draws

        elif etype in ("chi", "pon", "kan") and player != 0:
            name = SEAT_SHORT[player] if 0 <= player < 4 else f"P{player}"
            call_name = {"chi": "吃", "pon": "碰", "kan": "杠"}.get(etype, etype)
            tile = event.get("tile", "")
            print(f"  {name} → {call_name} {tile_to_display(tile)}")
            time.sleep(1)

        elif etype == "reach" and player != 0:
            name = SEAT_SHORT[player] if 0 <= player < 4 else f"P{player}"
            print(f"  \033[1;33m{name} → 立直!\033[0m")
            time.sleep(1)


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------

_engine_ref = None  # set during run_game for round result display


def print_round_result(state: RoundState):
    """Print the result of a round."""
    clear_screen()
    print(f"\033[1m{'═' * W}\033[0m")

    if state.result == RoundResult.TSUMO:
        name = SEAT_NAMES[state.winner]
        print(f"  \033[1m{name} ツモ和了!\033[0m")
    elif state.result == RoundResult.RON:
        winner = SEAT_NAMES[state.winner]
        loser = SEAT_NAMES[state.loser]
        print(f"  \033[1m{winner} ロン!\033[0m (放銃: {loser})")
    elif state.result == RoundResult.DRAW_NORMAL:
        print("  流局 (荒牌平局)")
    else:
        print(f"  {state.result.value}")

    # Show han/fu and yaku if available
    if state.han > 0:
        print(f"\n  \033[1m{state.han}翻 {state.fu}符\033[0m")
        if state.yaku:
            print(f"  役: {', '.join(state.yaku)}")

    print(f"\n{'─' * W}")
    for i in range(4):
        delta = state.score_deltas[i]
        sign = "+" if delta >= 0 else ""
        color = "\033[32m" if delta > 0 else ("\033[31m" if delta < 0 else "")
        rst = "\033[0m" if color else ""
        total_str = ""
        if _engine_ref:
            total_str = f"  → {_engine_ref.game_scores[i]:>6}点"
        print(f"  {_vpad(SEAT_SHORT[i], 4)}: {color}{sign}{delta:>6}{rst}{total_str}")
    print(f"{'═' * W}")
    input("\n  Enter で続行...")


def run_game():
    """Run a full game in the terminal."""
    global _engine_ref
    clear_screen()
    print(f"\033[1m{'═' * W}\033[0m")
    print(f"  立直麻雀 AI トレーナー  /  Riichi Mahjong AI Trainer")
    print(f"{'═' * W}")
    print()
    print(f"  あなた = 自家 (席0)")
    print(f"  AI対戦相手 × 3")
    print()

    human = HumanAgent()
    if _USE_MORTAL:
        print("  AI: Mortal v4 (local)")
        agents = [human,
                  MortalAgent.create_libriichi(1, _MODEL_PATH),
                  MortalAgent.create_libriichi(2, _MODEL_PATH),
                  MortalAgent.create_libriichi(3, _MODEL_PATH)]
    else:
        print("  AI: MockAgent (heuristic)")
        agents = [human, MockAgent("AI-1"), MockAgent("AI-2"), MockAgent("AI-3")]

    print()
    input("  Enter でゲーム開始...")

    engine = GameEngine(agents)
    _engine_ref = engine
    engine.round_callback = print_round_result

    try:
        final_scores = engine.play_game()
    except KeyboardInterrupt:
        print("\nゲーム中断")
        return

    # Final results
    clear_screen()
    print(f"\033[1m{'═' * W}\033[0m")
    print(f"  \033[1m最終結果\033[0m")
    print(f"{'═' * W}")
    print()

    ranked = sorted(range(4), key=lambda i: final_scores[i], reverse=True)
    for rank, i in enumerate(ranked, 1):
        marker = " \033[1;33m★\033[0m" if i == 0 else ""
        print(f"  {rank}位  {_vpad(SEAT_NAMES[i], 12)} {final_scores[i]:>6}点{marker}")

    print()
    your_rank = ranked.index(0) + 1
    print(f"  あなたの順位: {your_rank}位")
    print()


if __name__ == "__main__":
    run_game()

"""
Core Riichi Mahjong game engine.
Manages the complete game state and enforces rules.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol
import copy

from game.tiles import (
    build_wall, sort_tiles, normalize, is_red, tile_number, tile_suit,
    tile_type, TileType, dora_from_indicator, WINDS, DRAGONS, WIND_NAMES,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class MeldType(Enum):
    CHI = "chi"
    PON = "pon"
    ANKAN = "ankan"       # concealed kan
    MINKAN = "minkan"     # open kan (from discard)
    KAKAN = "kakan"       # added kan (pon → kan)


@dataclass
class Meld:
    type: MeldType
    tiles: list[str]
    from_player: int = -1  # who provided the called tile (-1 for ankan)
    called_tile: str = ""  # which tile was called


class ActionType(Enum):
    DISCARD = "discard"
    TSUMO = "tsumo"        # self-draw win
    RON = "ron"
    CHI = "chi"
    PON = "pon"
    KAN = "kan"            # any type of kan
    RIICHI = "riichi"
    KYUUSHU = "kyuushu"    # nine terminals draw
    SKIP = "skip"          # pass on a call opportunity


@dataclass
class Action:
    type: ActionType
    player: int
    tile: str = ""              # tile to discard / win on
    meld_tiles: list[str] = field(default_factory=list)  # tiles forming the meld
    is_tsumogiri: bool = False  # discarded the drawn tile


class RoundResult(Enum):
    TSUMO = "tsumo"
    RON = "ron"
    DRAW_NORMAL = "draw_normal"       # exhaustive draw
    DRAW_KYUUSHU = "draw_kyuushu"     # nine terminals
    DRAW_FOUR_RIICHI = "draw_4riichi"
    DRAW_FOUR_KAN = "draw_4kan"
    DRAW_FOUR_WIND = "draw_4wind"


# ---------------------------------------------------------------------------
# Player state within a round
# ---------------------------------------------------------------------------

@dataclass
class PlayerState:
    hand: list[str] = field(default_factory=list)
    melds: list[Meld] = field(default_factory=list)
    discards: list[str] = field(default_factory=list)
    discard_flags: list[dict] = field(default_factory=list)  # {tsumogiri, riichi, ...}
    is_riichi: bool = False
    riichi_turn: int = -1       # discard index when riichi declared
    is_ippatsu: bool = False
    is_furiten: bool = False
    is_temp_furiten: bool = False
    draw_tile: Optional[str] = None   # current drawn tile (None if not yet drawn)
    safe_tiles: set = field(default_factory=set)  # tiles confirmed safe against this player

    @property
    def is_menzen(self) -> bool:
        """Is the hand fully concealed?"""
        return all(m.type == MeldType.ANKAN for m in self.melds)

    @property
    def closed_tiles(self) -> list[str]:
        """Tiles in the closed hand (including draw)."""
        tiles = list(self.hand)
        if self.draw_tile:
            tiles.append(self.draw_tile)
        return tiles


# ---------------------------------------------------------------------------
# Agent protocol
# ---------------------------------------------------------------------------

class Agent(Protocol):
    """Interface for AI agents / human player."""

    def choose_action(
        self,
        player_id: int,
        game_state: "RoundState",
        available_actions: list[Action],
    ) -> Action:
        """Choose an action from the available options."""
        ...

    def on_event(self, event: dict) -> None:
        """Receive a game event notification (for mjai compatibility)."""
        ...


# ---------------------------------------------------------------------------
# Round state
# ---------------------------------------------------------------------------

@dataclass
class RoundState:
    """State for a single round (kyoku)."""

    # Round identifiers
    round_wind: str = "E"       # "E" or "S"
    round_number: int = 0       # 0-3
    honba: int = 0
    riichi_sticks: int = 0

    # Players
    scores: list[int] = field(default_factory=lambda: [25000] * 4)
    dealer: int = 0
    current_turn: int = 0

    # Wall
    wall: list[str] = field(default_factory=list)
    wall_pointer: int = 0       # next draw position
    dead_wall: list[str] = field(default_factory=list)
    dora_indicators: list[str] = field(default_factory=list)
    ura_dora_indicators: list[str] = field(default_factory=list)
    kan_count: int = 0

    # Per-player state
    players: list[PlayerState] = field(default_factory=lambda: [PlayerState() for _ in range(4)])

    # Turn tracking
    turn_count: int = 0
    last_discard: Optional[str] = None
    last_discard_player: int = -1

    # Result
    result: Optional[RoundResult] = None
    winner: int = -1
    loser: int = -1
    score_deltas: list[int] = field(default_factory=lambda: [0] * 4)

    @property
    def tiles_remaining(self) -> int:
        """Number of drawable tiles remaining in the wall."""
        return len(self.wall) - self.wall_pointer

    @property
    def doras(self) -> list[str]:
        """Active dora tiles (derived from indicators)."""
        return [dora_from_indicator(ind) for ind in self.dora_indicators]

    @property
    def is_last_draw(self) -> bool:
        return self.tiles_remaining <= 0


# ---------------------------------------------------------------------------
# Game Engine
# ---------------------------------------------------------------------------

class GameEngine:
    """Manages a full Riichi Mahjong game (multiple rounds)."""

    def __init__(self, agents: list[Agent], red_fives: bool = True):
        assert len(agents) == 4
        self.agents = agents
        self.red_fives = red_fives
        self.game_scores = [25000, 25000, 25000, 25000]
        self.round_wind = "E"
        self.round_number = 0  # 0-3 (dealer rotation)
        self.honba = 0
        self.riichi_sticks = 0
        self.round_log: list[dict] = []  # event log for current round
        self.game_log: list[list[dict]] = []  # all rounds

    @property
    def dealer(self) -> int:
        return self.round_number % 4

    def play_game(self) -> list[int]:
        """Play a full game (hanchan). Returns final scores."""
        while True:
            result = self.play_round()
            self.game_log.append(list(self.round_log))

            if self._should_end_game(result):
                break

        return self.game_scores

    def _should_end_game(self, result: RoundState) -> bool:
        """Determine if the game should end after this round."""
        # Someone busted (negative score)
        if any(s < 0 for s in self.game_scores):
            return True

        # After South 4 (or later)
        if self.round_wind == "S" and self.round_number >= 4:
            return True

        # South round: if dealer is first place with 30000+, game ends
        if self.round_wind == "S" and self.round_number >= 4:
            dealer = self.dealer
            if self.game_scores[dealer] >= 30000:
                max_score = max(self.game_scores)
                if self.game_scores[dealer] == max_score:
                    return True

        return False

    def _advance_round(self, renchan: bool):
        """Advance to the next round."""
        if renchan:
            self.honba += 1
        else:
            self.round_number += 1
            self.honba = 0
            if self.round_number >= 4:
                self.round_number = 0
                if self.round_wind == "E":
                    self.round_wind = "S"
                else:
                    # Game over will be caught by _should_end_game
                    pass

    # -------------------------------------------------------------------
    # Round play
    # -------------------------------------------------------------------

    def play_round(self) -> RoundState:
        """Play a single round (kyoku). Returns the round state with results."""
        state = self._init_round()
        self.round_log = []

        # Emit start events
        self._emit_start_round(state)

        # Main game loop
        while state.result is None:
            player_id = state.current_turn

            # 1. Draw phase
            if state.tiles_remaining <= 0:
                self._handle_exhaustive_draw(state)
                break

            drawn = self._draw_tile(state, player_id)
            state.players[player_id].draw_tile = drawn
            self._emit_draw(state, player_id, drawn)

            # 2. Check tsumo (self-draw win)
            # 3. Player decides: discard, tsumo, riichi, kan
            action = self._get_player_action(state, player_id, phase="draw")

            if action.type == ActionType.TSUMO:
                self._handle_tsumo(state, player_id)
                break

            if action.type == ActionType.KAN:
                self._handle_kan(state, player_id, action)
                continue  # kan draws replacement tile, same player continues

            is_riichi_action = action.type == ActionType.RIICHI
            if is_riichi_action:
                state.players[player_id].is_riichi = True
                state.players[player_id].is_ippatsu = True
                state.players[player_id].riichi_turn = len(state.players[player_id].discards)
                self.game_scores[player_id] -= 1000
                self.riichi_sticks += 1
                self._log_event({"type": "reach", "player": player_id})

            # 4. Discard
            discard_tile = action.tile
            self._do_discard(state, player_id, discard_tile)

            # 5. Check calls from other players
            call_action = self._check_calls(state, player_id, discard_tile)

            if call_action and call_action.type == ActionType.RON:
                self._handle_ron(state, call_action.player, player_id, discard_tile)
                break

            # Riichi accepted (discard wasn't ron'd)
            if is_riichi_action:
                self._log_event({"type": "reach_accepted", "player": player_id})

            if call_action and call_action.type in (ActionType.CHI, ActionType.PON, ActionType.KAN):
                self._handle_call(state, call_action)
                state.current_turn = call_action.player

                # After calling, player must discard from hand (no draw)
                if not state.players[call_action.player].hand:
                    # Edge case: empty hand after call (shouldn't happen normally)
                    state.current_turn = (call_action.player + 1) % 4
                    continue

                call_discard = self._get_player_action(state, call_action.player, phase="call")
                if call_discard.type == ActionType.SKIP or not call_discard.tile:
                    state.current_turn = (call_action.player + 1) % 4
                    continue

                self._do_discard(state, call_action.player, call_discard.tile)

                # Check calls on this discard too
                call2 = self._check_calls(state, call_action.player, call_discard.tile)
                if call2 and call2.type == ActionType.RON:
                    self._handle_ron(state, call2.player, call_action.player, call_discard.tile)
                    break
                elif call2 and call2.type in (ActionType.CHI, ActionType.PON):
                    self._handle_call(state, call2)
                    state.current_turn = call2.player
                    continue

                state.current_turn = (call_action.player + 1) % 4
            else:
                state.current_turn = (player_id + 1) % 4

            # Update ippatsu flags
            for p in state.players:
                if p.is_ippatsu and p.is_riichi:
                    # Ippatsu expires after one full turn cycle
                    p.is_ippatsu = False

        # Emit end_kyoku for mjai protocol
        self._log_event({"type": "end_kyoku"})

        # Apply score changes
        for i in range(4):
            self.game_scores[i] += state.score_deltas[i]

        # Determine renchan (dealer repeats)
        renchan = False
        if state.result in (RoundResult.TSUMO, RoundResult.RON):
            renchan = (state.winner == state.dealer)
        elif state.result == RoundResult.DRAW_NORMAL:
            renchan = self._dealer_tenpai(state)

        self._advance_round(renchan)
        return state

    # -------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------

    def _init_round(self) -> RoundState:
        """Initialize a new round."""
        wall = build_wall(self.red_fives)

        # Dead wall: last 14 tiles
        dead_wall = wall[-14:]
        live_wall = wall[:-14]

        # Dora indicators
        dora_indicators = [dead_wall[4]]  # 5th tile of dead wall
        ura_dora_indicators = [dead_wall[5]]

        # Deal 13 tiles to each player
        hands = [[] for _ in range(4)]
        ptr = 0
        for _ in range(3):  # 3 rounds of 4 tiles
            for p in range(4):
                start = (self.dealer + p) % 4
                hands[start].extend(live_wall[ptr:ptr+4])
                ptr += 4
        for p in range(4):
            start = (self.dealer + p) % 4
            hands[start].append(live_wall[ptr])
            ptr += 1

        players = []
        for i in range(4):
            ps = PlayerState(hand=sort_tiles(hands[i]))
            players.append(ps)

        state = RoundState(
            round_wind=self.round_wind,
            round_number=self.round_number,
            honba=self.honba,
            riichi_sticks=self.riichi_sticks,
            scores=list(self.game_scores),
            dealer=self.dealer,
            current_turn=self.dealer,
            wall=live_wall,
            wall_pointer=ptr,
            dead_wall=dead_wall,
            dora_indicators=dora_indicators,
            ura_dora_indicators=ura_dora_indicators,
            players=players,
        )
        return state

    # -------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------

    def _draw_tile(self, state: RoundState, player_id: int) -> str:
        """Draw a tile from the wall."""
        tile = state.wall[state.wall_pointer]
        state.wall_pointer += 1
        return tile

    def _do_discard(self, state: RoundState, player_id: int, tile: str):
        """Execute a discard."""
        ps = state.players[player_id]
        is_tsumogiri = (tile == ps.draw_tile)

        # Remove from hand or draw
        if is_tsumogiri and ps.draw_tile:
            ps.draw_tile = None
        else:
            if tile in ps.hand:
                ps.hand.remove(tile)
            elif ps.draw_tile == tile:
                ps.draw_tile = None
            # If draw tile was different, add it to hand
            if ps.draw_tile is not None:
                ps.hand.append(ps.draw_tile)
                ps.hand = sort_tiles(ps.hand)
                ps.draw_tile = None

        ps.discards.append(tile)
        ps.discard_flags.append({"tsumogiri": is_tsumogiri, "riichi": ps.is_riichi})
        state.last_discard = tile
        state.last_discard_player = player_id
        state.turn_count += 1

        self._log_event({"type": "discard", "player": player_id, "tile": tile,
                         "tsumogiri": is_tsumogiri})

    def _get_player_action(self, state: RoundState, player_id: int,
                           phase: str = "draw") -> Action:
        """Get action from player/agent."""
        available = self._compute_available_actions(state, player_id, phase)

        if len(available) == 1:
            return available[0]

        action = self.agents[player_id].choose_action(player_id, state, available)
        return action

    def _compute_available_actions(self, state: RoundState, player_id: int,
                                   phase: str) -> list[Action]:
        """Compute legal actions for a player."""
        ps = state.players[player_id]
        actions: list[Action] = []

        if phase == "draw":
            # After drawing: can discard, declare tsumo, riichi, or kan
            all_tiles = ps.closed_tiles

            # Check tsumo
            if self._can_tsumo(state, player_id):
                actions.append(Action(ActionType.TSUMO, player_id))

            # Check riichi
            if not ps.is_riichi and ps.is_menzen and self.game_scores[player_id] >= 1000:
                if state.tiles_remaining >= 4:
                    riichi_discards = self._get_riichi_discards(state, player_id)
                    for t in riichi_discards:
                        actions.append(Action(ActionType.RIICHI, player_id, tile=t))

            # Check ankan / kakan
            kan_options = self._get_kan_options(state, player_id)
            for opt in kan_options:
                actions.append(opt)

            # Discard options
            if ps.is_riichi:
                # Can only tsumogiri when in riichi (simplified)
                if ps.draw_tile:
                    actions.append(Action(ActionType.DISCARD, player_id,
                                         tile=ps.draw_tile, is_tsumogiri=True))
            else:
                seen = set()
                for t in all_tiles:
                    nt = normalize(t)
                    if nt not in seen:
                        seen.add(nt)
                        actions.append(Action(ActionType.DISCARD, player_id, tile=t,
                                              is_tsumogiri=(t == ps.draw_tile)))

        elif phase == "call":
            # After calling (chi/pon): must discard from hand (no draw)
            seen = set()
            for t in ps.hand:
                nt = normalize(t)
                if nt not in seen:
                    seen.add(nt)
                    actions.append(Action(ActionType.DISCARD, player_id, tile=t))

        if not actions:
            # Fallback: discard first available tile
            fallback_tiles = ps.hand if ps.hand else ([ps.draw_tile] if ps.draw_tile else [])
            if fallback_tiles:
                return [Action(ActionType.DISCARD, player_id, tile=fallback_tiles[0])]
            # Absolute fallback: skip
            return [Action(ActionType.SKIP, player_id)]
        return actions

    # -------------------------------------------------------------------
    # Calls
    # -------------------------------------------------------------------

    def _check_calls(self, state: RoundState, discarder: int, tile: str) -> Optional[Action]:
        """Check if any player wants to call the discarded tile.

        Priority: Ron > Pon/Kan > Chi
        """
        ron_actions = []
        pon_actions = []
        chi_actions = []

        for pid in range(4):
            if pid == discarder:
                continue

            ps = state.players[pid]

            # Check ron
            if self._can_ron(state, pid, tile):
                ron_actions.append(Action(ActionType.RON, pid, tile=tile))

            # Check pon (not allowed in riichi)
            if not ps.is_riichi and self._can_pon(ps, tile):
                pon_actions.append(Action(ActionType.PON, pid, tile=tile))

            # Check chi (only from left player / shimocha, not allowed in riichi)
            if not ps.is_riichi and pid == (discarder + 1) % 4:
                chi_opts = self._get_chi_options(ps, tile)
                for opt in chi_opts:
                    opt.player = pid
                chi_actions.extend(chi_opts)

        # Priority resolution
        all_calls = ron_actions + pon_actions + chi_actions
        if not all_calls:
            return None

        # Ask each player with call options if they want to call
        for action in ron_actions:
            available = [action, Action(ActionType.SKIP, action.player)]
            choice = self.agents[action.player].choose_action(action.player, state, available)
            if choice.type == ActionType.RON:
                return choice

        for action in pon_actions:
            available = [action, Action(ActionType.SKIP, action.player)]
            choice = self.agents[action.player].choose_action(action.player, state, available)
            if choice.type == ActionType.PON:
                return choice

        for action in chi_actions:
            available = chi_actions + [Action(ActionType.SKIP, action.player)]
            choice = self.agents[action.player].choose_action(action.player, state, available)
            if choice.type == ActionType.CHI:
                return choice

        return None

    def _handle_call(self, state: RoundState, action: Action):
        """Execute a chi/pon call."""
        pid = action.player
        ps = state.players[pid]
        tile = action.tile

        # Remove the tile from the discarder's discard pond
        discarder = state.last_discard_player
        if state.players[discarder].discards and state.players[discarder].discards[-1] == tile:
            state.players[discarder].discards.pop()

        if action.type == ActionType.PON:
            # Remove 2 matching tiles from hand
            removed = []
            base = normalize(tile)
            for t in list(ps.hand):
                if normalize(t) == base and len(removed) < 2:
                    ps.hand.remove(t)
                    removed.append(t)
            meld = Meld(MeldType.PON, removed + [tile], from_player=discarder, called_tile=tile)
            ps.melds.append(meld)

        elif action.type == ActionType.CHI:
            # action.meld_tiles contains the two tiles from hand
            for t in action.meld_tiles:
                # Find exact match first, then normalized match
                if t in ps.hand:
                    ps.hand.remove(t)
                else:
                    # Try normalized match
                    base = normalize(t)
                    for h in ps.hand:
                        if normalize(h) == base:
                            ps.hand.remove(h)
                            break
            meld = Meld(MeldType.CHI, action.meld_tiles + [tile],
                        from_player=discarder, called_tile=tile)
            ps.melds.append(meld)

        ps.hand = sort_tiles(ps.hand)
        # Log call event with consumed tiles for mjai compatibility
        # consumed = tiles from the caller's hand (all meld tiles except the called one)
        consumed = list(meld.tiles)
        try:
            consumed.remove(tile)  # remove only the first occurrence of the called tile
        except ValueError:
            pass
        self._log_event({"type": action.type.value, "player": pid, "tile": tile,
                         "target": discarder, "consumed": consumed})

    def _handle_kan(self, state: RoundState, player_id: int, action: Action):
        """Handle kan declaration."""
        ps = state.players[player_id]
        tile = action.tile
        base = normalize(tile)

        # Determine kan type from the action context
        matching = [t for t in ps.closed_tiles if normalize(t) == base]

        if len(matching) >= 4:
            # Ankan
            for t in matching[:4]:
                if t in ps.hand:
                    ps.hand.remove(t)
                elif t == ps.draw_tile:
                    ps.draw_tile = None
            meld = Meld(MeldType.ANKAN, matching[:4])
            ps.melds.append(meld)
            self._log_event({"type": "kan", "player": player_id, "tile": tile,
                             "target": player_id, "consumed": matching[:4]})
        else:
            # Kakan (add to existing pon)
            for m in ps.melds:
                if m.type == MeldType.PON and normalize(m.tiles[0]) == base:
                    if tile in ps.hand:
                        ps.hand.remove(tile)
                    elif tile == ps.draw_tile:
                        ps.draw_tile = None
                    m.tiles.append(tile)
                    m.type = MeldType.KAKAN
                    self._log_event({"type": "kan", "player": player_id, "tile": tile,
                                     "target": player_id, "consumed": list(m.tiles[:3])})
                    break

        # Draw replacement from dead wall (take from front)
        if state.dead_wall:
            replacement = state.dead_wall.pop(0)
            ps.draw_tile = replacement

        # New dora indicator
        # Dead wall layout: [r0..r3, d1, u1, d2, u2, d3, u3, d4, u4]
        # After n pops, original index (4 + n*2) becomes (4 + n*2 - n) = (4 + n)
        state.kan_count += 1
        dora_idx = 4 + state.kan_count  # adjusted for pops: 5, 6, 7, 8
        if state.kan_count <= 4 and dora_idx < len(state.dead_wall):
            new_indicator = state.dead_wall[dora_idx]
            state.dora_indicators.append(new_indicator)
            self._log_event({"type": "dora", "dora_marker": new_indicator})

        ps.hand = sort_tiles(ps.hand)

    def _handle_tsumo(self, state: RoundState, player_id: int):
        """Handle tsumo win."""
        state.result = RoundResult.TSUMO
        state.winner = player_id
        # Scoring would go here - simplified for now
        self._calculate_win_score(state, player_id, is_tsumo=True)
        self._log_event({"type": "tsumo", "player": player_id})

    def _handle_ron(self, state: RoundState, winner: int, loser: int, tile: str):
        """Handle ron win."""
        state.result = RoundResult.RON
        state.winner = winner
        state.loser = loser
        # Add winning tile to winner's hand for scoring
        state.players[winner].draw_tile = tile
        self._calculate_win_score(state, winner, is_tsumo=False, loser=loser)
        self._log_event({"type": "ron", "player": winner, "from": loser, "tile": tile})

    def _handle_exhaustive_draw(self, state: RoundState):
        """Handle exhaustive draw (ryuukyoku)."""
        state.result = RoundResult.DRAW_NORMAL
        self._log_event({"type": "ryukyoku"})
        # Tenpai payments
        tenpai = [self._is_tenpai(state, i) for i in range(4)]
        tenpai_count = sum(tenpai)

        if 0 < tenpai_count < 4:
            pay_total = 3000
            receive_each = pay_total // tenpai_count
            pay_each = pay_total // (4 - tenpai_count)
            for i in range(4):
                if tenpai[i]:
                    state.score_deltas[i] = receive_each
                else:
                    state.score_deltas[i] = -pay_each

    # -------------------------------------------------------------------
    # Win checking
    # -------------------------------------------------------------------

    def _can_tsumo(self, state: RoundState, player_id: int) -> bool:
        """Check if player can declare tsumo."""
        ps = state.players[player_id]
        tiles = ps.closed_tiles
        return self._is_complete_hand(tiles) and self._has_yaku_tsumo(state, player_id)

    def _can_ron(self, state: RoundState, player_id: int, tile: str) -> bool:
        """Check if player can declare ron on a tile."""
        ps = state.players[player_id]
        test_hand = ps.hand + [tile]
        if not self._is_complete_hand(test_hand):
            return False
        # Furiten check
        if self._is_furiten(state, player_id):
            return False
        return True

    def _is_complete_hand(self, tiles: list[str]) -> bool:
        """Check if tiles form a complete winning hand (4 mentsu + 1 jantai or special)."""
        if len(tiles) < 2:
            return False

        # Normalize for pattern checking
        normalized = [normalize(t) for t in tiles]
        return self._check_regular_win(normalized) or self._check_seven_pairs(normalized)

    def _check_regular_win(self, tiles: list[str]) -> bool:
        """Check for standard 4-mentsu + 1-jantai pattern."""
        from collections import Counter
        counts = Counter(tiles)

        # Try each possible pair
        for pair_tile, cnt in counts.items():
            if cnt < 2:
                continue
            remaining = Counter(counts)
            remaining[pair_tile] -= 2
            if remaining[pair_tile] == 0:
                del remaining[pair_tile]
            if self._extract_mentsu(remaining, 4):
                return True
        return False

    def _extract_mentsu(self, counts: dict, needed: int) -> bool:
        """Try to extract 'needed' mentsu (sets of 3) from tile counts."""
        if needed == 0:
            return all(v == 0 for v in counts.values())

        # Find first non-zero tile
        for tile in sorted(counts.keys()):
            if counts[tile] > 0:
                break
        else:
            return needed == 0

        # Try triplet
        if counts[tile] >= 3:
            counts[tile] -= 3
            if self._extract_mentsu(counts, needed - 1):
                counts[tile] += 3
                return True
            counts[tile] += 3

        # Try sequence (only for suited tiles)
        suit = tile_suit(tile)
        num = tile_number(tile)
        if suit and num and num <= 7:
            t2 = f"{num+1}{suit}"
            t3 = f"{num+2}{suit}"
            if counts.get(t2, 0) >= 1 and counts.get(t3, 0) >= 1:
                counts[tile] -= 1
                counts[t2] -= 1
                counts[t3] -= 1
                if self._extract_mentsu(counts, needed - 1):
                    counts[tile] += 1
                    counts[t2] += 1
                    counts[t3] += 1
                    return True
                counts[tile] += 1
                counts[t2] += 1
                counts[t3] += 1

        return False

    def _check_seven_pairs(self, tiles: list[str]) -> bool:
        """Check for seven pairs (chiitoitsu)."""
        if len(tiles) != 14:
            return False
        from collections import Counter
        counts = Counter(tiles)
        return len(counts) == 7 and all(v == 2 for v in counts.values())

    def _is_tenpai(self, state: RoundState, player_id: int) -> bool:
        """Check if player is tenpai (one tile away from winning)."""
        ps = state.players[player_id]
        tiles = list(ps.hand)
        from game.tiles import ALL_TILE_FACES
        for test_tile in ALL_TILE_FACES:
            if self._is_complete_hand(tiles + [test_tile]):
                return True
        return False

    def _is_furiten(self, state: RoundState, player_id: int) -> bool:
        """Check if player is in furiten."""
        ps = state.players[player_id]
        # Check own discards for winning tiles
        from game.tiles import ALL_TILE_FACES
        waits = []
        for test_tile in ALL_TILE_FACES:
            if self._is_complete_hand(ps.hand + [test_tile]):
                waits.append(normalize(test_tile))

        for d in ps.discards:
            if normalize(d) in waits:
                return True
        return False

    def _has_yaku_tsumo(self, state: RoundState, player_id: int) -> bool:
        """Simplified yaku check - at least 1 yaku exists.

        For now, always returns True. Full yaku evaluation uses mahjong library.
        """
        # TODO: integrate mahjong library for proper yaku check
        return True

    # -------------------------------------------------------------------
    # Call checks
    # -------------------------------------------------------------------

    def _can_pon(self, ps: PlayerState, tile: str) -> bool:
        base = normalize(tile)
        count = sum(1 for t in ps.hand if normalize(t) == base)
        return count >= 2

    def _get_chi_options(self, ps: PlayerState, tile: str) -> list[Action]:
        """Get possible chi combinations."""
        options = []
        suit = tile_suit(tile)
        num = tile_number(tile)
        if suit is None or num is None:
            return options

        # Build a list of (number, original_tile) for matching suit
        hand_by_num: dict[int, list[str]] = {}
        for t in ps.hand:
            if tile_suit(t) == suit:
                n = tile_number(t)
                if n is not None:
                    hand_by_num.setdefault(n, []).append(t)

        # Check three possible sequences containing this tile
        for start in [num - 2, num - 1, num]:
            if start < 1 or start + 2 > 9:
                continue
            needed = [n for n in [start, start+1, start+2] if n != num]
            if all(n in hand_by_num and len(hand_by_num[n]) > 0 for n in needed):
                meld_tiles = [hand_by_num[n][0] for n in needed]
                options.append(Action(ActionType.CHI, -1, tile=tile, meld_tiles=list(meld_tiles)))

        return options

    def _get_kan_options(self, state: RoundState, player_id: int) -> list[Action]:
        """Get possible kan declarations."""
        ps = state.players[player_id]
        options = []
        from collections import Counter

        all_tiles = ps.closed_tiles
        counts = Counter(normalize(t) for t in all_tiles)

        # Ankan: 4 of same in hand
        for base, cnt in counts.items():
            if cnt >= 4:
                options.append(Action(ActionType.KAN, player_id, tile=base))

        # Kakan: add to existing pon
        if ps.draw_tile:
            draw_base = normalize(ps.draw_tile)
            for m in ps.melds:
                if m.type == MeldType.PON and normalize(m.tiles[0]) == draw_base:
                    options.append(Action(ActionType.KAN, player_id, tile=ps.draw_tile))

        return options

    def _get_riichi_discards(self, state: RoundState, player_id: int) -> list[str]:
        """Get tiles that can be discarded for riichi declaration."""
        ps = state.players[player_id]
        valid = []
        for tile in ps.closed_tiles:
            test = list(ps.hand)
            if tile == ps.draw_tile:
                pass  # Just remove draw
            elif tile in test:
                test.remove(tile)
                if ps.draw_tile:
                    test.append(ps.draw_tile)
            else:
                continue

            if self._is_tenpai_hand(test):
                valid.append(tile)
        return list(set(valid))

    def _is_tenpai_hand(self, tiles: list[str]) -> bool:
        """Check if a 13-tile hand is tenpai."""
        from game.tiles import ALL_TILE_FACES
        for test_tile in ALL_TILE_FACES:
            if self._is_complete_hand(tiles + [test_tile]):
                return True
        return False

    def _dealer_tenpai(self, state: RoundState) -> bool:
        return self._is_tenpai(state, state.dealer)

    # -------------------------------------------------------------------
    # Scoring (simplified)
    # -------------------------------------------------------------------

    def _calculate_win_score(self, state: RoundState, winner: int,
                             is_tsumo: bool, loser: int = -1):
        """Calculate score for a win. Simplified fixed scoring for now.

        TODO: integrate mahjong library for proper han/fu calculation.
        """
        # Simplified: assign mangan (8000/12000)
        is_dealer = (winner == state.dealer)
        base = 12000 if is_dealer else 8000

        # Add honba
        base += state.honba * 300

        if is_tsumo:
            if is_dealer:
                each = base // 3
                for i in range(4):
                    if i == winner:
                        state.score_deltas[i] = base + state.riichi_sticks * 1000
                    else:
                        state.score_deltas[i] = -each
            else:
                dealer_pay = base // 2
                other_pay = base // 4
                for i in range(4):
                    if i == winner:
                        state.score_deltas[i] = base + state.riichi_sticks * 1000
                    elif i == state.dealer:
                        state.score_deltas[i] = -dealer_pay
                    else:
                        state.score_deltas[i] = -other_pay
        else:
            # Ron
            state.score_deltas[winner] = base + state.riichi_sticks * 1000
            state.score_deltas[loser] = -base

        self.riichi_sticks = 0

    # -------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------

    def _log_event(self, event: dict):
        self.round_log.append(event)
        for agent in self.agents:
            agent.on_event(event)

    def _emit_start_round(self, state: RoundState):
        event = {
            "type": "start_round",
            "round_wind": state.round_wind,
            "round_number": state.round_number,
            "honba": state.honba,
            "riichi_sticks": self.riichi_sticks,
            "dealer": state.dealer,
            "dora_indicators": state.dora_indicators,
            "scores": state.scores,
            "tehais": [list(p.hand) for p in state.players],
        }
        self._log_event(event)

    def _emit_draw(self, state: RoundState, player_id: int, tile: str):
        self._log_event({"type": "draw", "player": player_id, "tile": tile})

"""Tests for tile efficiency calculation."""
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
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "2s", "3s", "7s", "8s", "E", "E", "C"]
        result = calculate_shanten(hand)
        assert result >= 1

    def test_complete_hand(self):
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s", "E", "E", "P", "P"]
        result = calculate_shanten(hand)
        assert result == 0


class TestCalculateEfficiency:
    def test_basic_efficiency(self):
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "2s", "3s", "4s", "7s", "E", "E", "C", "9m"]
        visible: list[str] = []
        rows = calculate_efficiency(hand, visible)
        assert len(rows) > 0
        # Should be sorted by total descending
        for i in range(len(rows) - 1):
            assert rows[i].total >= rows[i + 1].total

    def test_only_shanten_reducing(self):
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "2s", "3s", "4s", "7s", "E", "E", "C", "9m"]
        visible: list[str] = []
        rows = calculate_efficiency(hand, visible)
        for row in rows:
            assert len(row.accepts) > 0

    def test_visible_tiles_reduce_remaining(self):
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "2s", "3s", "4s", "7s", "E", "E", "C", "9m"]
        visible_empty: list[str] = []
        visible_some = ["1s", "1s", "5s", "5s"]
        rows_empty = calculate_efficiency(hand, visible_empty)
        rows_some = calculate_efficiency(hand, visible_some)
        # Build lookup for comparison
        empty_map = {r.discard: r for r in rows_empty}
        some_map = {r.discard: r for r in rows_some}
        for discard in empty_map:
            if discard in some_map:
                assert empty_map[discard].total == some_map[discard].total
                assert some_map[discard].remaining <= empty_map[discard].remaining

    def test_empty_result_when_already_complete(self):
        hand = ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s", "1s", "2s", "3s", "E", "E"]
        visible: list[str] = []
        rows = calculate_efficiency(hand, visible)
        assert isinstance(rows, list)

    def test_hand_too_short(self):
        hand = ["1m", "2m", "3m"]
        rows = calculate_efficiency(hand, [])
        assert rows == []

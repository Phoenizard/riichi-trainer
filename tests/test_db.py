"""Tests for database logging."""
import os
import tempfile
import pytest
from backend.db import GameLogger


@pytest.fixture
def logger():
    """Create a GameLogger with a temporary database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    lg = GameLogger(db_path=path)
    yield lg
    lg.close()
    os.unlink(path)


class TestGameLogger:
    def test_start_game(self, logger):
        game_id = logger.start_game()
        assert isinstance(game_id, str)
        assert len(game_id) == 8

    def test_end_game(self, logger):
        game_id = logger.start_game()
        logger.end_game(game_id, [25000, 25000, 25000, 25000], 1)
        cur = logger._conn.execute("SELECT ended_at, placement FROM games WHERE id = ?", (game_id,))
        row = cur.fetchone()
        assert row[0] is not None  # ended_at set
        assert row[1] == 1

    def test_log_decision(self, logger):
        game_id = logger.start_game()
        round_id = logger.start_round(game_id, 0)
        logger.log_decision(
            round_id=round_id,
            turn_number=0,
            action_type="discard",
            player_action="1m",
            ai_recommendation="3m",
            ai_action_type="dahai",
            match=False,
            shanten=2,
            hand=["1m", "2m", "3m"],
        )
        cur = logger._conn.execute("SELECT * FROM decisions WHERE round_id = ?", (round_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[4] == "1m"  # player_action
        assert row[5] == "3m"  # ai_recommendation
        assert row[7] == 0     # match = False

    def test_get_round_stats(self, logger):
        game_id = logger.start_game()
        round_id = logger.start_round(game_id, 0)
        # Log 3 decisions: 2 match, 1 doesn't
        for i, (action, rec, m) in enumerate([
            ("1m", "1m", True),
            ("2m", "3m", False),
            ("5p", "5p", True),
        ]):
            logger.log_decision(round_id, i, "discard", action, rec, "dahai", m, 1, None)

        stats = logger.get_round_stats(round_id)
        assert stats["total"] == 3
        assert stats["matches"] == 2
        assert abs(stats["agreement_rate"] - 2/3) < 0.01

    def test_empty_round_stats(self, logger):
        stats = logger.get_round_stats("nonexistent")
        assert stats["total"] == 0
        assert stats["matches"] == 0
        assert stats["agreement_rate"] == 0.0

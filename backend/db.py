"""
SQLite database logging for game decisions and results.

Records every decision point (player choice vs AI recommendation),
round results, and game outcomes for future review and analysis.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from game.engine import RoundState


_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    final_scores TEXT,
    placement INTEGER
);

CREATE TABLE IF NOT EXISTS rounds (
    id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES games(id),
    round_index INTEGER NOT NULL,
    round_wind TEXT,
    round_number INTEGER,
    honba INTEGER,
    result_type TEXT,
    winner INTEGER,
    loser INTEGER,
    han INTEGER,
    fu INTEGER,
    yaku TEXT,
    score_deltas TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL REFERENCES rounds(id),
    turn_number INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    player_action TEXT,
    ai_recommendation TEXT,
    ai_action_type TEXT,
    match INTEGER NOT NULL DEFAULT 0,
    shanten INTEGER,
    hand TEXT
);
"""


class GameLogger:
    """Logs game data to SQLite for review and analysis."""

    def __init__(self, db_path: str = "data/games.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def start_game(self) -> str:
        """Create a new game record. Returns game_id."""
        game_id = str(uuid.uuid4())[:8]
        self._conn.execute(
            "INSERT INTO games (id, started_at) VALUES (?, ?)",
            (game_id, datetime.now().isoformat()),
        )
        self._conn.commit()
        return game_id

    def start_round(self, game_id: str, round_index: int) -> str:
        """Create a round record at the start of a round. Returns round_id."""
        round_id = f"{game_id}-r{round_index}"
        self._conn.execute(
            "INSERT INTO rounds (id, game_id, round_index) VALUES (?, ?, ?)",
            (round_id, game_id, round_index),
        )
        self._conn.commit()
        return round_id

    def end_round(self, round_id: str, state: RoundState) -> None:
        """Update a round record with results."""
        self._conn.execute(
            """UPDATE rounds SET
               round_wind = ?, round_number = ?, honba = ?,
               result_type = ?, winner = ?, loser = ?,
               han = ?, fu = ?, yaku = ?, score_deltas = ?
               WHERE id = ?""",
            (
                state.round_wind,
                state.round_number,
                state.honba,
                state.result.value if state.result else None,
                state.winner,
                state.loser,
                state.han,
                state.fu,
                json.dumps(state.yaku) if state.yaku else None,
                json.dumps(state.score_deltas) if state.score_deltas else None,
                round_id,
            ),
        )
        self._conn.commit()

    def log_decision(
        self,
        round_id: str,
        turn_number: int,
        action_type: str,
        player_action: str,
        ai_recommendation: Optional[str],
        ai_action_type: Optional[str],
        match: bool,
        shanten: Optional[int],
        hand: Optional[list[str]],
    ) -> None:
        """Log a single decision point."""
        self._conn.execute(
            """INSERT INTO decisions
               (round_id, turn_number, action_type, player_action,
                ai_recommendation, ai_action_type, match, shanten, hand)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                round_id,
                turn_number,
                action_type,
                player_action,
                ai_recommendation,
                ai_action_type,
                1 if match else 0,
                shanten,
                json.dumps(hand) if hand else None,
            ),
        )
        self._conn.commit()

    def get_round_stats(self, round_id: str) -> dict:
        """Get decision stats for a round."""
        cur = self._conn.execute(
            "SELECT COUNT(*), SUM(match) FROM decisions WHERE round_id = ?",
            (round_id,),
        )
        total, matches = cur.fetchone()
        matches = matches or 0
        return {
            "total": total,
            "matches": matches,
            "agreement_rate": matches / total if total > 0 else 0.0,
        }

    def end_game(self, game_id: str, final_scores: list[int], placement: int) -> None:
        """Finalize a game record."""
        self._conn.execute(
            "UPDATE games SET ended_at = ?, final_scores = ?, placement = ? WHERE id = ?",
            (datetime.now().isoformat(), json.dumps(final_scores), placement, game_id),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

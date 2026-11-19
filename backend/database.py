"""SQLite persistence for a local prototype (no external database needed)."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def database_path():
    return Path(os.environ.get("SNOOZE_DB_PATH", Path(__file__).parent / "sleep.db"))


@contextmanager
def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS nights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id TEXT NOT NULL,
                bedtime TEXT NOT NULL,
                wake_time TEXT NOT NULL,
                sleep_hours REAL NOT NULL,
                snoozes INTEGER NOT NULL,
                restedness INTEGER NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS pending_bedtimes (
                participant_id TEXT PRIMARY KEY,
                bedtime TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_nights_participant ON nights(participant_id, wake_time)")


def insert_night(night):
    hours = round((night.wake_time - night.bedtime).total_seconds() / 3600, 3)
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO nights(participant_id, bedtime, wake_time, sleep_hours, snoozes, restedness) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (night.participant_id, night.bedtime.isoformat(), night.wake_time.isoformat(),
             hours, night.snoozes, night.restedness),
        )
        return cursor.lastrowid


def nights_for(participant_id):
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM nights WHERE participant_id = ? ORDER BY wake_time, id",
            (participant_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def all_nights():
    with connect() as db:
        rows = db.execute("SELECT * FROM nights ORDER BY participant_id, wake_time, id").fetchall()
        return [dict(row) for row in rows]


def start_bedtime(participant_id, bedtime):
    with connect() as db:
        db.execute(
            "INSERT INTO pending_bedtimes(participant_id, bedtime) VALUES (?, ?) "
            "ON CONFLICT(participant_id) DO UPDATE SET bedtime = excluded.bedtime",
            (participant_id, bedtime.isoformat()),
        )


def finish_bedtime(participant_id, wake_time, snoozes, restedness):
    """Atomically move a pending bedtime to a complete night, if it exists."""
    from schemas import NightIn
    from datetime import datetime

    with connect() as db:
        pending = db.execute(
            "SELECT bedtime FROM pending_bedtimes WHERE participant_id = ?", (participant_id,)
        ).fetchone()
        if pending is None:
            return None
        night = NightIn(
            participant_id=participant_id,
            bedtime=datetime.fromisoformat(pending["bedtime"]),
            wake_time=wake_time,
            snoozes=snoozes,
            restedness=restedness,
        )
        hours = round((night.wake_time - night.bedtime).total_seconds() / 3600, 3)
        cursor = db.execute(
            "INSERT INTO nights(participant_id, bedtime, wake_time, sleep_hours, snoozes, restedness) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (participant_id, night.bedtime.isoformat(), night.wake_time.isoformat(),
             hours, snoozes, restedness),
        )
        db.execute("DELETE FROM pending_bedtimes WHERE participant_id = ?", (participant_id,))
        return cursor.lastrowid

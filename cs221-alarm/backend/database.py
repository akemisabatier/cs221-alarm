"""SQLite persistence for a local prototype (no external database needed)."""

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
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
        _migrate(db)


# Columns the web app needs: a client-generated id (so the offline queue can retry
# a save without creating duplicates), exact epoch-millisecond timestamps, and the
# phone's UTC offset.
_EXTRA_COLUMNS = {
    "client_id": "TEXT",
    "bed_ms": "INTEGER",
    "wake_ms": "INTEGER",
    "tz_offset_min": "INTEGER NOT NULL DEFAULT 0",
}


def _migrate(db):
    existing = {row["name"] for row in db.execute("PRAGMA table_info(nights)")}
    for name, ddl in _EXTRA_COLUMNS.items():
        if name not in existing:
            db.execute(f"ALTER TABLE nights ADD COLUMN {name} {ddl}")
    # Backfill rows written before these columns existed.
    for row in db.execute(
        "SELECT id, bedtime, wake_time FROM nights WHERE client_id IS NULL OR bed_ms IS NULL"
    ).fetchall():
        db.execute(
            "UPDATE nights SET client_id = COALESCE(client_id, ?), "
            "bed_ms = COALESCE(bed_ms, ?), wake_ms = COALESCE(wake_ms, ?) WHERE id = ?",
            (f"legacy-{row['id']}", _to_ms(datetime.fromisoformat(row["bedtime"])),
             _to_ms(datetime.fromisoformat(row["wake_time"])), row["id"]),
        )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_nights_client "
        "ON nights(participant_id, client_id)"
    )


def _to_ms(moment):
    """Epoch milliseconds. A naive datetime is read as the server's local time."""
    return int(round(moment.timestamp() * 1000))


def _local_iso(ms, tz_offset_min):
    """Wall-clock ISO string on the participant's phone (offset as in JS getTimezoneOffset)."""
    utc = datetime.fromtimestamp(ms / 1000 - tz_offset_min * 60, tz=timezone.utc)
    return utc.replace(tzinfo=None).isoformat(timespec="seconds")


def insert_night(night):
    hours = round((night.wake_time - night.bedtime).total_seconds() / 3600, 3)
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO nights(participant_id, bedtime, wake_time, sleep_hours, snoozes, restedness, "
            "client_id, bed_ms, wake_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (night.participant_id, night.bedtime.isoformat(), night.wake_time.isoformat(),
             hours, night.snoozes, night.restedness,
             uuid.uuid4().hex, _to_ms(night.bedtime), _to_ms(night.wake_time)),
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
            "INSERT INTO nights(participant_id, bedtime, wake_time, sleep_hours, snoozes, restedness, "
            "client_id, bed_ms, wake_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (participant_id, night.bedtime.isoformat(), night.wake_time.isoformat(),
             hours, snoozes, restedness,
             uuid.uuid4().hex, _to_ms(night.bedtime), _to_ms(night.wake_time)),
        )
        db.execute("DELETE FROM pending_bedtimes WHERE participant_id = ?", (participant_id,))
        return cursor.lastrowid


def upsert_night(participant_id, client_id, bed_ms, wake_ms, snoozes, restedness, tz_offset_min=0):
    """Create or overwrite one night identified by (participant, client_id).

    Idempotent, so the app's offline queue can safely retry. Returns True if created.
    """
    hours = round((wake_ms - bed_ms) / 3600000, 3)
    values = (
        _local_iso(bed_ms, tz_offset_min), _local_iso(wake_ms, tz_offset_min),
        hours, snoozes, restedness, bed_ms, wake_ms, tz_offset_min,
    )
    with connect() as db:
        exists = db.execute(
            "SELECT 1 FROM nights WHERE participant_id = ? AND client_id = ?",
            (participant_id, client_id),
        ).fetchone() is not None
        db.execute(
            "INSERT INTO nights(participant_id, client_id, bedtime, wake_time, sleep_hours, snoozes, "
            "restedness, bed_ms, wake_ms, tz_offset_min) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(participant_id, client_id) DO UPDATE SET "
            "bedtime = excluded.bedtime, wake_time = excluded.wake_time, "
            "sleep_hours = excluded.sleep_hours, snoozes = excluded.snoozes, "
            "restedness = excluded.restedness, bed_ms = excluded.bed_ms, "
            "wake_ms = excluded.wake_ms, tz_offset_min = excluded.tz_offset_min",
            (participant_id, client_id) + values,
        )
        return not exists


def delete_night(participant_id, client_id):
    """Delete one night. Returns how many rows were removed (0 if already gone)."""
    with connect() as db:
        cursor = db.execute(
            "DELETE FROM nights WHERE participant_id = ? AND client_id = ?",
            (participant_id, client_id),
        )
        return cursor.rowcount

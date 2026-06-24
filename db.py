from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_RATES: dict[str, float] = {
    "Partner": 900,
    "Managing Director": 750,
    "Senior Manager": 500,
    "Manager": 350,
    "Senior Staff": 300,
    "Staff": 225,
    "Intern": 125,
    "Project Services": 175,
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def db_path() -> Path:
    override = os.environ.get("BUDGET_TRACKER_DB")
    if override:
        return Path(override).resolve()
    return app_dir() / "budget_tracker.db"


def seed_path() -> Path:
    seed_name = os.environ.get("BUDGET_TRACKER_SEED", "demo_seed.db")
    return app_dir() / seed_name


def schema_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "schema.sql"  # type: ignore[attr-defined]
    return app_dir() / "schema.sql"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):  # type: ignore[override]
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or db_path(), factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | None = None) -> Path:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(target) as conn:
        conn.executescript(schema_path().read_text(encoding="utf-8"))
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            ("bill_rates", json.dumps(DEFAULT_RATES)),
        )
    return target

def load_seed_database(path: Path | None = None) -> Path:
    target = path or db_path()
    seed = seed_path()
    if not seed.exists():
        raise FileNotFoundError(f"Demo seed database not found: {seed}")
    if seed.resolve() == target.resolve():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_name(f"{target.name}.loading")
    shutil.copyfile(seed, temp_target)
    os.replace(temp_target, target)
    init_db(target)
    return target

def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) or {} for row in rows]


def get_rates(conn: sqlite3.Connection) -> dict[str, float]:
    row = conn.execute("SELECT value FROM settings WHERE key = 'bill_rates'").fetchone()
    if not row:
        return DEFAULT_RATES.copy()
    try:
        data = json.loads(row["value"])
    except json.JSONDecodeError:
        return DEFAULT_RATES.copy()
    return {str(key): float(value or 0) for key, value in data.items()}


def set_rates(conn: sqlite3.Connection, rates: dict[str, Any]) -> dict[str, float]:
    clean = {str(key): float(value or 0) for key, value in rates.items()}
    conn.execute(
        """
        INSERT INTO settings(key, value) VALUES ('bill_rates', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (json.dumps(clean),),
    )
    return clean


def backup_database(destination: Path) -> Path:
    init_db()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path(), destination)
    return destination


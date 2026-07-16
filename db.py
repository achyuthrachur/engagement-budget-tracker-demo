from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3
DEFAULT_RATES = {
    "Partner FY26": 900,
    "Managing Director FY26": 750,
    "Senior Manager FY26": 500,
    "Manager FY26": 350,
    "Senior Staff FY26": 300,
    "Staff FY26": 225,
    "Intern FY26": 125,
    "Project Services FY26": 175,
    "Offshore Senior Manager FY26": 300,
    "Offshore Manager FY26": 225,
    "Offshore Staff FY26": 125,
    "Partner": 900,
    "Managing Director": 750,
    "Senior Manager": 500,
    "Manager": 350,
    "Senior Staff": 300,
    "Staff": 225,
    "Intern": 125,
    "Project Services": 175,
}
DEFAULT_SETTINGS = {
    "bill_rates": json.dumps(DEFAULT_RATES),
    "engagement_discount_rate": "0",
    "contract_discount_rate": "0",
    "variance_threshold_hours": "6",
    "variance_threshold_pct": "1.0",
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    override = os.environ.get("BUDGET_TRACKER_DATA_DIR")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA") or app_dir())
        return base / "Crowe" / "B2A Budget Tracker"
    return app_dir()


def db_path() -> Path:
    override = os.environ.get("BUDGET_TRACKER_DB")
    return Path(override).resolve() if override else data_dir() / "budget_tracker.db"


def seed_path() -> Path:
    return app_dir() / os.environ.get("BUDGET_TRACKER_SEED", "demo_seed.db")


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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def init_db(path: Path | None = None) -> Path:
    target = path or db_path()
    if getattr(sys, "frozen", False) and not target.exists():
        portable = app_dir() / "budget_tracker.db"
        if portable.exists() and portable.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(portable, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(target) as conn:
        legacy = _table_exists(conn, "engagements") and "complexity_mode" not in _columns(
            conn, "engagements"
        )
    if legacy:
        backup = target.with_name(f"{target.stem}.pre-v2.bak{target.suffix}")
        if not backup.exists():
            shutil.copy2(target, backup)
        from migrations import migrate_v1_to_v2
        migrate_v1_to_v2(target, schema_path(), now_iso())

    with connect(target) as conn:
        conn.executescript(schema_path().read_text(encoding="utf-8"))
        if "is_active" not in _columns(conn, "team_members"):
            conn.execute("ALTER TABLE team_members ADD COLUMN is_active INTEGER DEFAULT 1 CHECK (is_active IN (0,1))")
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, now_iso()),
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
    return {key: row[key] for key in row.keys()} if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) or {} for row in rows]


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_rates(conn: sqlite3.Connection) -> dict[str, float]:
    try:
        data = json.loads(get_setting(conn, "bill_rates", json.dumps(DEFAULT_RATES)))
    except (json.JSONDecodeError, TypeError):
        return DEFAULT_RATES.copy()
    return {str(key): float(value or 0) for key, value in data.items()}


def set_rates(conn: sqlite3.Connection, rates: dict[str, Any]) -> dict[str, float]:
    clean = {str(key): float(value or 0) for key, value in rates.items()}
    set_setting(conn, "bill_rates", json.dumps(clean))
    return clean


def get_app_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "rates": get_rates(conn),
        "engagement_discount_rate": float(get_setting(conn, "engagement_discount_rate", 0) or 0),
        "contract_discount_rate": float(get_setting(conn, "contract_discount_rate", 0) or 0),
        "variance_threshold_hours": float(get_setting(conn, "variance_threshold_hours", 6) or 6),
        "variance_threshold_pct": float(get_setting(conn, "variance_threshold_pct", 1.0) or 1.0),
    }


def backup_database(destination: Path) -> Path:
    init_db()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path(), destination)
    return destination


def automatic_backup(path: Path | None = None, label: str = "automatic") -> Path | None:
    source = path or db_path()
    if not source.exists():
        return None
    folder = source.parent / "Backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = folder / f"budget_tracker_{label}_{stamp}.db"
    shutil.copy2(source, destination)
    backups = sorted(folder.glob("budget_tracker_*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in backups[20:]:
        stale.unlink(missing_ok=True)
    return destination


def latest_backup(path: Path | None = None) -> Path | None:
    source = path or db_path()
    folder = source.parent / "Backups"
    if not folder.exists():
        return None
    backups = sorted(folder.glob("budget_tracker_*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    return backups[0] if backups else None

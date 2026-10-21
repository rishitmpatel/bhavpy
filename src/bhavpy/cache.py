"""Local SQLite cache.

One file (``<cache_dir>/bhavpy.sqlite``) holds every parsed dataset, a fetch log that
records which days were downloaded (or confirmed missing, e.g. holidays), and a small
blob store for snapshot files such as symbol lists. Repeat requests never touch the
network, and ``bhavpy update`` only fetches days the log does not have yet.

SQLite ships with Python, works the same on Linux/macOS/Windows and needs no server.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from .config import settings

#: Bump when a table layout changes incompatibly.
SCHEMA_VERSION = 1

_local = threading.local()
_write_lock = threading.RLock()
_tables_ready: set[tuple[str, str]] = set()

_BASE_DDL = """
CREATE TABLE IF NOT EXISTS fetch_log (
    dataset TEXT NOT NULL,
    day TEXT NOT NULL,
    status TEXT NOT NULL,          -- 'ok' | 'missing'
    rows INTEGER NOT NULL DEFAULT 0,
    fetched_at REAL NOT NULL,
    PRIMARY KEY (dataset, day)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS blobs (
    key TEXT PRIMARY KEY,
    data BLOB NOT NULL,
    fetched_at REAL NOT NULL
);
"""


def path() -> Path:
    return Path(settings.cache_dir) / "bhavpy.sqlite"


def connect() -> sqlite3.Connection:
    """Per-thread connection to the cache database (created on first use)."""
    con: sqlite3.Connection | None = getattr(_local, "con", None)
    p = path()
    if con is not None and getattr(_local, "path", None) == p:
        return con
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=60, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(_BASE_DDL)
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    elif version != SCHEMA_VERSION:
        raise RuntimeError(
            f"cache at {p} uses schema v{version}, this bhavpy expects v{SCHEMA_VERSION}; "
            "run `bhavpy cache clear` (or point BHAVPY_CACHE_DIR elsewhere)"
        )
    _local.con = con
    _local.path = p
    return con


def reset() -> None:
    """Forget open connections (after the cache directory changes)."""
    con = getattr(_local, "con", None)
    if con is not None:
        con.close()
    _local.__dict__.clear()
    _tables_ready.clear()


def ensure_table(name: str, ddl: str) -> None:
    key = (str(path()), name)
    if key in _tables_ready:
        return
    with _write_lock:
        connect().executescript(ddl)
    _tables_ready.add(key)


def write_frame(table: str, df: pd.DataFrame, columns: Sequence[str]) -> int:
    """Insert-or-replace rows of ``df[columns]`` into ``table``."""
    if df.empty:
        return 0
    data = df.loc[:, list(columns)]
    data = data.astype(object).where(pd.notna(data), None)
    rows = [tuple(r) for r in data.itertuples(index=False, name=None)]
    cols = ",".join(f'"{c}"' for c in columns)
    marks = ",".join("?" * len(columns))
    with _write_lock:
        con = connect()
        con.executemany(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", rows)
        con.commit()
    return len(rows)


def query(sql: str, params: Iterable[Any] = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, connect(), params=list(params))


def execute(sql: str, params: Iterable[Any] = ()) -> None:
    with _write_lock:
        con = connect()
        con.execute(sql, list(params))
        con.commit()


# ---------------------------------------------------------------- fetch log


def log_fetch(dataset: str, day: dt.date, status: str, rows: int = 0) -> None:
    execute(
        "INSERT OR REPLACE INTO fetch_log (dataset, day, status, rows, fetched_at) VALUES (?,?,?,?,?)",
        (dataset, day.isoformat(), status, rows, time.time()),
    )


def fetched_days(dataset: str, start: dt.date, end: dt.date) -> dict[dt.date, str]:
    """Days in [start, end] that are already settled for ``dataset`` -> status."""
    cur = connect().execute(
        "SELECT day, status FROM fetch_log WHERE dataset=? AND day BETWEEN ? AND ?",
        (dataset, start.isoformat(), end.isoformat()),
    )
    return {dt.date.fromisoformat(d): s for d, s in cur.fetchall()}


def last_day(dataset: str, status: str = "ok") -> dt.date | None:
    row = (
        connect()
        .execute("SELECT MAX(day) FROM fetch_log WHERE dataset=? AND status=?", (dataset, status))
        .fetchone()
    )
    return dt.date.fromisoformat(row[0]) if row and row[0] else None


# ---------------------------------------------------------------- blobs


def blob_get(key: str, max_age_hours: float | None = None) -> bytes | None:
    row = connect().execute("SELECT data, fetched_at FROM blobs WHERE key=?", (key,)).fetchone()
    if row is None:
        return None
    data, fetched_at = row
    stale = max_age_hours is not None and time.time() - fetched_at > max_age_hours * 3600
    if stale and not settings.offline:
        return None
    return bytes(data)


def blob_put(key: str, data: bytes) -> None:
    execute(
        "INSERT OR REPLACE INTO blobs (key, data, fetched_at) VALUES (?,?,?)",
        (key, sqlite3.Binary(data), time.time()),
    )


def cached_blob(key: str, fetch: Callable[[], bytes], max_age_hours: float | None) -> bytes:
    """Return a fresh-enough cached blob, else fetch, store and return it.

    If fetching fails and a stale copy exists, the stale copy is returned so offline
    or blocked sessions keep working.
    """
    hit = blob_get(key, max_age_hours)
    if hit is not None:
        return hit
    try:
        data = fetch()
    except Exception:
        stale = blob_get(key, None)
        if stale is not None:
            return stale
        raise
    blob_put(key, data)
    return data


# ---------------------------------------------------------------- housekeeping


def info() -> dict[str, Any]:
    """Size of the cache and row counts per table."""
    con = connect()
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    datasets = {
        ds: {"days": n, "first": lo, "last": hi}
        for ds, n, lo, hi in con.execute(
            "SELECT dataset, COUNT(*), MIN(day), MAX(day) FROM fetch_log WHERE status='ok' GROUP BY dataset"
        )
    }
    p = path()
    size = sum(f.stat().st_size for f in p.parent.glob(p.name + "*") if f.exists())
    return {"path": str(p), "size_mb": round(size / 1e6, 2), "tables": counts, "datasets": datasets}


def vacuum() -> None:
    """Compact the database file after large deletions."""
    with _write_lock:
        connect().execute("VACUUM")


def clear(dataset: str | None = None) -> None:
    """Delete everything, or just one dataset's fetch-log entries (forces a re-download)."""
    if dataset:
        execute("DELETE FROM fetch_log WHERE dataset=?", (dataset,))
        return
    reset()
    p = path()
    for f in p.parent.glob(p.name + "*"):
        f.unlink(missing_ok=True)

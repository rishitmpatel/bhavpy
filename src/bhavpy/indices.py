"""Index constituents: current (NSE Indices files) and point-in-time.

Point-in-time membership avoids survivorship bias in backtests:

* **NIFTY 50** - reconstructed by walking NSE's published index changes (bundled in
  ``data/nifty50_changes.csv``, each row citing the NSE press release) back from today's
  list. Covers 2016-04-01 onwards; the walk is verified to keep exactly 50 names.
* **Other indices** - bhavpy stores a dated snapshot each time it downloads a list, so
  history builds up from your first use (or from a scheduled ``bhavpy update``).
"""

from __future__ import annotations

import datetime as dt
import functools
from importlib import resources

import pandas as pd

from . import cache, http
from .config import settings
from .dates import DateLike, to_date, today_ist
from .errors import NotAvailable
from .sources import niftyindices
from .sources.nse_indices import canonical_index

_SNAP_DDL = """
CREATE TABLE IF NOT EXISTS index_snapshots (
    "index" TEXT NOT NULL, as_of TEXT NOT NULL, symbol TEXT NOT NULL, name TEXT,
    industry TEXT, isin TEXT,
    PRIMARY KEY ("index", as_of, symbol)
) WITHOUT ROWID;
"""


def available() -> list[str]:
    """Indices with a downloadable constituent list."""
    return sorted(niftyindices.FILES)


def _current(index: str) -> pd.DataFrame:
    if index not in niftyindices.FILES:
        raise NotAvailable(f"no constituent file known for {index!r}; available: {available()}")
    url = niftyindices.url_for(index)
    raw = cache.cached_blob(f"constituents:{index}", lambda: http.get(url, expect="csv"), settings.ttl_hours)
    df = niftyindices.parse(raw)
    cache.ensure_table("index_snapshots", _SNAP_DDL)
    snap = df.assign(index=index, as_of=today_ist().isoformat())
    cache.write_frame("index_snapshots", snap, ["index", "as_of", "symbol", "name", "industry", "isin"])
    return df


@functools.lru_cache(maxsize=1)
def nifty50_changes() -> pd.DataFrame:
    """Bundled NIFTY 50 change log: effective_date, removed, added, source."""
    with resources.files("bhavpy.data").joinpath("nifty50_changes.csv").open("r", encoding="utf-8") as fh:
        df = pd.read_csv(fh, dtype=str, keep_default_na=False, comment="#")
    return df


NIFTY50_HISTORY_START = dt.date(2016, 4, 1)


def nifty50_members(as_of: dt.date, current: set[str]) -> set[str]:
    """Walk the change log back from ``current`` to the membership on ``as_of``."""
    members = set(current)
    ch = nifty50_changes().sort_values("effective_date", ascending=False)
    for row in ch.itertuples(index=False):
        eff = dt.date.fromisoformat(row.effective_date)
        if eff <= as_of:
            break
        members.discard(row.added)
        members.add(row.removed)
    return members


def constituents(index: str = "NIFTY 50", as_of: DateLike = None) -> pd.DataFrame:
    """Members of ``index`` today, or on ``as_of`` where history allows.

    Returns columns ``symbol, name, industry, isin`` (``name``/``industry``/``isin`` may
    be empty for historical members that have since left the index).
    """
    key = canonical_index(index)
    today = today_ist()
    day = to_date(as_of, today)
    cur = _current(key)
    if day >= today:
        return cur.drop(columns=["series"], errors="ignore")
    if key == "NIFTY 50":
        if day < NIFTY50_HISTORY_START:
            raise NotAvailable(f"bundled NIFTY 50 history starts {NIFTY50_HISTORY_START}")
        members = nifty50_members(day, set(cur["symbol"]))
        known = cur.set_index("symbol")
        rows = [
            {
                "symbol": s,
                **({k: known.at[s, k] for k in ("name", "industry", "isin")} if s in known.index else {}),
            }
            for s in sorted(members)
        ]
        return pd.DataFrame(rows, columns=["symbol", "name", "industry", "isin"])
    cache.ensure_table("index_snapshots", _SNAP_DDL)
    snaps = cache.query(
        'SELECT * FROM index_snapshots WHERE "index" = ? AND as_of <= ? ORDER BY as_of DESC',
        (key, day.isoformat()),
    )
    if snaps.empty:
        first = cache.query('SELECT MIN(as_of) AS d FROM index_snapshots WHERE "index" = ?', (key,))[
            "d"
        ].iloc[0]
        raise NotAvailable(
            f"no stored snapshot of {key} on or before {day}; earliest stored is {first}. "
            "Run `bhavpy update` regularly to build point-in-time history for this index."
        )
    latest = snaps["as_of"].iloc[0]
    return snaps[snaps["as_of"] == latest][["symbol", "name", "industry", "isin"]].reset_index(drop=True)

"""Institutional flows and large trades: FII/DII cash activity, bulk and block deals."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from . import cache, http
from .config import settings
from .dates import DateLike, ist_index, to_date, today_ist
from .sources import nse_deals, nse_fiidii

_FLOW_DDL = """
CREATE TABLE IF NOT EXISTS fii_dii (
    date TEXT NOT NULL, category TEXT NOT NULL, buy REAL, sell REAL, net REAL,
    PRIMARY KEY (date, category)
) WITHOUT ROWID;
"""
_DEAL_DDL = """
CREATE TABLE IF NOT EXISTS deals (
    date TEXT NOT NULL, kind TEXT NOT NULL, symbol TEXT NOT NULL, security_name TEXT,
    client TEXT NOT NULL, side TEXT NOT NULL, quantity REAL NOT NULL, price REAL,
    remarks TEXT,
    PRIMARY KEY (date, kind, symbol, client, side, quantity, price)
) WITHOUT ROWID;
"""


def fii_dii() -> pd.DataFrame:
    """Latest FII/FPI and DII provisional cash-market activity (Rs crore).

    Each call also stores the day in the cache; :func:`fii_dii_history` returns everything
    stored so far (NSE publishes only the latest day).
    """
    cache.ensure_table("fii_dii", _FLOW_DDL)
    raw = cache.cached_blob("fii_dii_latest", lambda: http.get(nse_fiidii.URL, expect="json"), 1.0)
    df = nse_fiidii.parse(raw)
    cache.write_frame("fii_dii", df, nse_fiidii.COLUMNS)
    df.index = ist_index(pd.to_datetime(df.pop("date")))
    return df


def fii_dii_history(start: DateLike = None, end: DateLike = None) -> pd.DataFrame:
    """All FII/DII days stored in the cache (wide: fii_buy, fii_sell, fii_net, dii_...)."""
    cache.ensure_table("fii_dii", _FLOW_DDL)
    s = to_date(start, dt.date(2000, 1, 1)).isoformat()
    e = to_date(end, today_ist()).isoformat()
    df = cache.query("SELECT * FROM fii_dii WHERE date BETWEEN ? AND ? ORDER BY date", (s, e))
    if df.empty:
        return pd.DataFrame(index=ist_index([]))
    wide = df.pivot(index="date", columns="category", values=["buy", "sell", "net"])
    wide.columns = [f"{c.lower().replace('/', '_')}_{v}" for v, c in wide.columns]
    wide.index = ist_index(pd.to_datetime(wide.index))
    return wide.sort_index(axis=1)


def _deals(kind: str, start: DateLike, end: DateLike) -> pd.DataFrame:
    cache.ensure_table("deals", _DEAL_DDL)
    e = to_date(end, today_ist())
    s = to_date(start, e - dt.timedelta(days=30))
    dataset = f"deals_{kind}"
    seen = cache.fetched_days(dataset, s, e)
    day = s
    while day <= e:
        chunk_end = min(day + dt.timedelta(days=89), e)
        need = any(d not in seen for d in pd.date_range(day, chunk_end).date)
        if need and not settings.offline:
            raw = http.get(
                nse_deals.HISTORY_URL,
                expect="json",
                params=nse_deals.history_params(
                    kind, day.strftime("%d-%m-%Y"), chunk_end.strftime("%d-%m-%Y")
                ),
            )
            df = nse_deals.parse_history(raw, kind)
            cache.write_frame("deals", df.dropna(subset=["date"]), nse_deals.COLUMNS)
            for d in pd.date_range(day, chunk_end).date:
                if (today_ist() - d).days >= 2:
                    cache.log_fetch(dataset, d, "ok")
        day = chunk_end + dt.timedelta(days=1)
    out = cache.query(
        "SELECT * FROM deals WHERE kind = ? AND date BETWEEN ? AND ? ORDER BY date, symbol",
        (kind, s.isoformat(), e.isoformat()),
    )
    out.index = ist_index(pd.to_datetime(out.pop("date")))
    return out


def bulk_deals(start: DateLike = None, end: DateLike = None) -> pd.DataFrame:
    """NSE bulk deals (>0.5% of shares in one client's trades in a day). Default: last 30 days."""
    return _deals("bulk", start, end)


def block_deals(start: DateLike = None, end: DateLike = None) -> pd.DataFrame:
    """NSE block deals (single trades >= Rs 10 crore in the block window). Default: last 30 days."""
    return _deals("block", start, end)

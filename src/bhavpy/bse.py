"""BSE daily equity data and NSE <-> BSE mapping by ISIN."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from . import calendar, store
from .dates import DateLike, ist_index, to_date, today_ist
from .errors import NotAvailable, SymbolNotFound
from .sources.bse_cm import BseCmBhavcopy

BSE = BseCmBhavcopy()


def ensure(start: DateLike, end: DateLike = None) -> dict[str, int]:
    s = to_date(start)
    e = to_date(end, today_ist())
    # BSE and NSE share the trading calendar.
    return store.ensure(BSE, calendar.candidate_days(s, e))


def bhavcopy(day: DateLike = None) -> pd.DataFrame:
    """Whole BSE equity bhavcopy for one day (default: latest available)."""
    d = to_date(day, today_ist())
    got = pd.DataFrame()
    for _ in range(1 if day is not None else 10):
        store.ensure(BSE, [d])
        got = store.read_range(BSE, d, d)
        if not got.empty:
            break
        d -= dt.timedelta(days=1)
    if got.empty:
        raise NotAvailable(f"no BSE bhavcopy for {d}")
    got.index = ist_index(pd.to_datetime(got.pop("date")))
    return got


def history(code: str, start: DateLike = None, end: DateLike = None) -> pd.DataFrame:
    """Daily OHLCV for a BSE security by scrip code (``"500325"``), ISIN, or BSE ticker.

    BSE tickers exist in the files only from 2024-07-08; scrip code and ISIN work for the
    whole archive. Prices are unadjusted (corporate actions: use the NSE series).
    """
    e = to_date(end, today_ist())
    s = to_date(start, e - dt.timedelta(days=365))
    ensure(s, e)
    key = code.strip().upper()
    if key.isdigit():
        where, params = "scrip_code = ?", (key,)
    elif len(key) == 12 and key[:2].isalpha() and key[2:].isalnum():
        where, params = "isin = ?", (key,)
    else:
        # Map ticker -> scrip code via the newest file that has tickers.
        hit = store.read_range(BSE, dt.date(2024, 7, 8), e, "symbol = ?", (key,))
        if hit.empty:
            raise SymbolNotFound(f"BSE ticker {code!r} not found; try the scrip code or ISIN")
        where, params = "scrip_code = ?", (hit["scrip_code"].iloc[-1],)
    df = store.read_range(BSE, s, e, where, params)
    if df.empty:
        raise SymbolNotFound(f"no BSE rows for {code!r} between {s} and {e}")
    df.index = ist_index(pd.to_datetime(df.pop("date")))
    return df


def nse_bse_map(day: DateLike = None) -> pd.DataFrame:
    """Securities listed on both exchanges, joined by ISIN.

    Columns: ``isin, nse_symbol, nse_series, bse_code, bse_symbol, bse_group, name``.
    """
    from . import equity

    nse = equity.market(day, series=None).reset_index()
    bse = bhavcopy(day if day is not None else nse["date"].iloc[0].date())
    nse = nse[nse["isin"].notna()][["isin", "symbol", "series"]].drop_duplicates("isin")
    b = bse[bse["isin"].notna()][["isin", "scrip_code", "symbol", "group", "name"]].drop_duplicates("isin")
    m = nse.merge(b, on="isin", suffixes=("_nse", "_bse"))
    return m.rename(
        columns={
            "symbol_nse": "nse_symbol",
            "series": "nse_series",
            "scrip_code": "bse_code",
            "symbol_bse": "bse_symbol",
            "group": "bse_group",
        }
    )[["isin", "nse_symbol", "nse_series", "bse_code", "bse_symbol", "bse_group", "name"]].reset_index(
        drop=True
    )

"""Futures & options: daily bhavcopy, futures history, live option chain, lots, expiries."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from . import cache, calendar, http, store
from .config import settings
from .dates import DateLike, ist_index, to_date, today_ist
from .errors import NotAvailable
from .sources import nse_lots, nse_options
from .sources.nse_fo import NseFoBhavcopy

FO = NseFoBhavcopy()

_EXP_DDL = """
CREATE TABLE IF NOT EXISTS fo_expiries (
    symbol TEXT NOT NULL, instrument TEXT NOT NULL, expiry TEXT NOT NULL,
    PRIMARY KEY (symbol, instrument, expiry)
) WITHOUT ROWID;
"""


def _raw_file(d: dt.date) -> bytes:
    def fetch() -> bytes:
        last: Exception | None = None
        for url in FO.urls(d):
            try:
                return http.get(url, expect="zip")
            except NotAvailable as exc:
                last = exc
        raise NotAvailable(f"no NSE F&O bhavcopy for {d}") from last

    return cache.cached_blob(f"fo_raw:{d.isoformat()}", fetch, max_age_hours=None)


def bhavcopy(day: DateLike = None) -> pd.DataFrame:
    """Full F&O bhavcopy for one day (default: latest available): futures and options.

    The raw file is cached once (~1 MB/day); futures rows also go into the futures table.
    """
    d = to_date(day, today_ist())
    raw: bytes | None = None
    for _ in range(1 if day is not None else 10):
        try:
            raw = _raw_file(d)
            break
        except NotAvailable:
            if day is not None:
                raise
            d -= dt.timedelta(days=1)
    if raw is None:
        raise NotAvailable(f"no NSE F&O bhavcopy in the 10 days up to {to_date(day, today_ist())}")
    got = FO.parse(raw, d)
    if d not in cache.fetched_days(FO.dataset, d, d):
        store._store(FO, d, got)
    _record_expiries(got)
    got.index = ist_index(pd.to_datetime(got.pop("date")))
    return got


def _record_expiries(df: pd.DataFrame) -> None:
    cache.ensure_table("fo_expiries", _EXP_DDL)
    exp = df[["symbol", "instrument", "expiry"]].dropna().drop_duplicates()
    cache.write_frame("fo_expiries", exp, ["symbol", "instrument", "expiry"])


def futures(
    symbol: str, start: DateLike = None, end: DateLike = None, *, expiry: str = "near"
) -> pd.DataFrame:
    """Daily futures OHLC/OI for ``symbol``.

    ``expiry``: ``"near"`` / ``"next"`` / ``"far"`` for a continuous series built from the
    1st/2nd/3rd contract on each day, or ``"all"`` for every contract.
    """
    e = to_date(end, today_ist())
    s = to_date(start, e - dt.timedelta(days=90))
    store.ensure(FO, calendar.candidate_days(s, e))
    df = store.read_range(FO, s, e, "symbol = ? AND instrument LIKE 'FUT%'", (symbol.upper(),))
    if df.empty:
        raise NotAvailable(f"no futures rows for {symbol} between {s} and {e}")
    df = df.sort_values(["date", "expiry"])
    if expiry != "all":
        rank = {"near": 0, "next": 1, "far": 2}[expiry]
        df = df.groupby("date", group_keys=False).nth(rank)
    df.index = ist_index(pd.to_datetime(df.pop("date")))
    return df.drop(columns=["strike", "option_type"])


def options(symbol: str, day: DateLike = None, expiry: DateLike = None) -> pd.DataFrame:
    """End-of-day option rows for ``symbol`` on one day (from the bhavcopy)."""
    df = bhavcopy(day)
    df = df[(df["symbol"] == symbol.upper()) & df["instrument"].str.startswith("OPT")]
    if expiry is not None:
        df = df[df["expiry"] == to_date(expiry).isoformat()]
    return df.sort_values(["expiry", "strike", "option_type"])


def expiries(symbol: str = "NIFTY") -> list[dt.date]:
    """Upcoming expiries (live, from NSE's option-chain contract info)."""
    raw = cache.cached_blob(
        f"oc_expiries:{symbol.upper()}",
        lambda: http.get(nse_options.CONTRACT_INFO_URL, expect="json", params={"symbol": symbol.upper()}),
        max_age_hours=1,
    )
    return [dt.date.fromisoformat(x) for x in nse_options.parse_expiries(raw)]


def expiry_calendar(symbol: str = "NIFTY", start: DateLike = None, end: DateLike = None) -> pd.DataFrame:
    """Historical + scheduled expiry dates for ``symbol``'s derivatives.

    Built from F&O bhavcopies sampled once a week (every listed expiry appears in each
    day's file), so a decade costs ~500 downloads once, then it is cached.
    """
    e = to_date(end, today_ist())
    s = to_date(start, e - dt.timedelta(days=365))
    days = calendar.trading_days(s, min(e, today_ist()))
    weekly = pd.Series(days, index=days).groupby(days.to_period("W")).last()
    for ts in weekly:
        d = ts.date()
        settled = cache.fetched_days("fo_expiries", d, d)
        if d in settled:
            continue
        try:
            raw_df = store.fetch_day(FO, d)
        except NotAvailable:
            continue
        _record_expiries(raw_df)
        cache.log_fetch("fo_expiries", d, "ok", len(raw_df))
    cache.ensure_table("fo_expiries", _EXP_DDL)
    out = cache.query(
        "SELECT expiry, instrument FROM fo_expiries WHERE symbol = ? AND expiry BETWEEN ? AND ?",
        (symbol.upper(), s.isoformat(), e.isoformat()),
    )
    if out.empty:
        return pd.DataFrame(columns=["futures", "options", "monthly"], index=ist_index([]))
    piv = out.assign(kind=out["instrument"].str[:3]).pivot_table(
        index="expiry", columns="kind", values="instrument", aggfunc="count"
    )
    res = pd.DataFrame(index=ist_index(pd.to_datetime(piv.index)))
    res["futures"] = (piv.get("FUT", pd.Series(dtype=float)).fillna(0) > 0).to_numpy()
    res["options"] = (piv.get("OPT", pd.Series(dtype=float)).fillna(0) > 0).to_numpy()
    res["monthly"] = res["futures"]  # futures only list monthly contracts
    return res.sort_index()


def option_chain(symbol: str = "NIFTY", expiry: DateLike = None) -> pd.DataFrame:
    """Live option-chain snapshot (long format: one row per strike x CE/PE).

    This is the one dataset that only exists on NSE's live site; it is fetched with a
    normal browser-like request and never cached for more than a minute. ``df.attrs``
    holds ``timestamp`` and ``underlying_price``.
    """
    sym = symbol.upper()
    exp = to_date(expiry) if expiry is not None else expiries(sym)[0]
    params = nse_options.chain_params(sym, exp.strftime("%d-%b-%Y"))
    raw = cache.cached_blob(
        f"oc:{sym}:{exp.isoformat()}",
        lambda: http.get(nse_options.CHAIN_URL, expect="json", params=params),
        max_age_hours=1 / 60,
    )
    df, meta = nse_options.parse_chain(raw)
    df["expiry"] = ist_index(pd.to_datetime(df["expiry"])) if len(df) else df["expiry"]
    df.attrs.update(meta)
    df.attrs["symbol"] = sym
    return df


def lot_sizes() -> pd.DataFrame:
    """Current F&O lot sizes per symbol and contract month (long format)."""
    raw = cache.cached_blob("fo_mktlots", lambda: http.get(nse_lots.URL, expect="csv"), settings.ttl_hours)
    return nse_lots.parse(raw)

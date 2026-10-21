"""Daily OHLCV history for NSE stocks and indices, raw and corporate-action adjusted."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import pandas as pd

from . import adjust as _adjust
from . import calendar, store, symbols
from .dates import DateLike, ist_index, to_date, today_ist
from .errors import NotAvailable, SymbolNotFound
from .sources.nse_cm import NseCmBhavcopy
from .sources.nse_indices import ALIASES, NseIndexClose, canonical_index

CM = NseCmBhavcopy()
INDEX = NseIndexClose()

#: Series preference when a stock has rows in several series on one day.
SERIES_ORDER = ("EQ", "BE", "BZ", "BT", "SM", "ST", "SZ", "RR", "IV", "E1")

PRICE_COLUMNS = [
    "symbol", "series", "isin", "open", "high", "low", "close", "last", "prev_close",
    "volume", "turnover", "trades",
]  # fmt: skip


def _default_start(end: dt.date) -> dt.date:
    return end - dt.timedelta(days=365)


def ensure_market(start: DateLike, end: DateLike = None) -> dict[str, int]:
    """Download (once) every NSE equity bhavcopy in the range into the cache."""
    s = to_date(start)
    e = to_date(end, today_ist())
    return store.ensure(CM, calendar.candidate_days(s, e))


def ensure_indices(start: DateLike, end: DateLike = None) -> dict[str, int]:
    s = max(to_date(start), INDEX.first_date)
    e = to_date(end, today_ist())
    return store.ensure(INDEX, calendar.candidate_days(s, e))


def is_index(name: str) -> bool:
    key = canonical_index(name)
    return " " in name.strip() or key in ALIASES.values() or name.strip().upper() in ALIASES


def raw_history(
    symbol: str, start: dt.date, end: dt.date, series: Sequence[str] | None = None
) -> pd.DataFrame:
    """Unadjusted daily rows for a stock across all its historical tickers."""
    ensure_market(start, end)
    chain = symbols.symbol_chain(symbol)
    frames = []
    for seg in chain:
        s = max(start, seg.start) if seg.start else start
        e = min(end, seg.end - dt.timedelta(days=1)) if seg.end else end
        if s > e:
            continue
        got = store.read_range(CM, s, e, "symbol = ?", (seg.symbol,))
        if not got.empty:  # empty frames have object dtypes and would poison the concat
            frames.append(got)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", *PRICE_COLUMNS])
    if series:
        df = df[df["series"].isin(list(series))]
    if df.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS, index=ist_index([]))
    rank = {s: i for i, s in enumerate(SERIES_ORDER)}
    df = df.assign(_r=df["series"].map(rank).fillna(99)).sort_values(["date", "_r"])
    df = df.drop_duplicates("date", keep="first").drop(columns="_r")
    df.index = ist_index(pd.to_datetime(df.pop("date")))
    return df[PRICE_COLUMNS]


def history(
    symbol: str,
    start: DateLike = None,
    end: DateLike = None,
    *,
    adjust: str | None = "split",
    series: Sequence[str] | None = None,
    infer: bool | None = None,
    on_mismatch: str = "skip",
    demerger: str = "estimate",
) -> pd.DataFrame:
    """Daily OHLCV for an NSE stock (or index) from the official bhavcopy archive.

    Parameters
    ----------
    symbol:
        NSE ticker (``"RELIANCE"``), an old ticker (``"ZOMATO"``), or an index name
        (``"NIFTY 50"``, ``"BANKNIFTY"``, ``"INDIA VIX"``).
    start, end:
        Any date-like; default is the last 365 days.
    adjust:
        ``"split"`` (default) adjusts for splits, bonuses, consolidations and rights;
        ``"total"`` also for dividends (use for return calculations); ``None`` = raw only.
        Adjusted prices are expressed in the share terms of the **last row** returned.
    demerger:
        ``"estimate"`` (default) adjusts demergers/schemes using the ex-date price
        discovery (flagged ``check="estimated"``); ``"ignore"`` leaves them unadjusted.
    series:
        Restrict to series, e.g. ``["EQ"]``. Default picks the best series per day
        (EQ, then BE, BZ, ...), so stocks moved to trade-to-trade stay continuous.

    Returns
    -------
    DataFrame indexed by IST date with raw ``open high low close last prev_close volume
    turnover trades`` and, when adjusted, ``adj_open adj_high adj_low adj_close
    adj_volume adj_factor``. ``df.attrs["events"]`` holds the factor table.
    """
    e = to_date(end, today_ist())
    s = to_date(start, _default_start(e))
    if s > e:
        raise ValueError(f"start {s} is after end {e}")
    if is_index(symbol):
        return index_history(symbol, s, e)
    raw = raw_history(symbol, s, e, series)
    if raw.empty:
        info = symbols.symbol_chain(symbol)
        raise SymbolNotFound(
            f"no NSE equity rows for {symbol!r} between {s} and {e} "
            f"(tickers tried: {[x.symbol for x in info]}). Check the symbol or the date range."
        )
    if adjust in (None, "none", "raw", False):
        return raw
    if adjust not in ("split", "total"):
        raise ValueError("adjust must be 'split', 'total' or None")
    actions = _adjust.corporate_actions(symbol)
    events = _adjust.build_events(
        actions, raw, mode=adjust, infer=infer, on_mismatch=on_mismatch, demerger=demerger
    )
    events = events[(events["ex_date"] > raw.index[0]) & (events["ex_date"] <= raw.index[-1])]
    out = _adjust.apply(raw, events)
    out.attrs["events"] = events.reset_index(drop=True)
    out.attrs["adjust"] = adjust
    return out


def factors(
    symbol: str,
    start: DateLike = None,
    end: DateLike = None,
    *,
    adjust: str = "split",
    infer: bool | None = None,
    on_mismatch: str = "skip",
    demerger: str = "estimate",
) -> pd.DataFrame:
    """The adjustment-factor table behind :func:`history` (one row per event).

    Includes ``cumulative_factor``: the multiplier applied to prices before that ex-date.
    """
    df = history(symbol, start, end, adjust=adjust, infer=infer, on_mismatch=on_mismatch, demerger=demerger)
    ev = df.attrs.get("events")
    if ev is None or ev.empty:
        return pd.DataFrame(columns=[*_adjust.EVENT_COLUMNS, "cumulative_factor"])
    ev = ev.copy()
    before = ev["ex_date"] - pd.Timedelta(days=1)
    ev["cumulative_factor"] = _adjust.cumulative(pd.DatetimeIndex(before), ev).to_numpy()
    return ev


def index_history(name: str, start: DateLike = None, end: DateLike = None) -> pd.DataFrame:
    """Daily OHLC (+ volume, turnover, P/E, P/B, dividend yield) for an NSE index."""
    e = to_date(end, today_ist())
    s = to_date(start, _default_start(e))
    key = canonical_index(name)
    if e < INDEX.first_date:
        raise NotAvailable(f"NSE's index archive starts {INDEX.first_date}; no data for {name} before that")
    ensure_indices(s, e)
    df = store.read_range(INDEX, max(s, INDEX.first_date), e, '"index" = ?', (key,))
    if df.empty:
        raise SymbolNotFound(f"no rows for index {name!r} (canonical {key!r}) between {s} and {e}")
    df.index = ist_index(pd.to_datetime(df.pop("date")))
    return df


def market(day: DateLike = None, series: Sequence[str] | None = ("EQ",)) -> pd.DataFrame:
    """The whole NSE equity bhavcopy for one day (default: latest available)."""
    if day is None:
        d = today_ist()
        for _ in range(10):
            ensure_market(d, d)
            got = store.read_range(CM, d, d)
            if not got.empty:
                break
            d -= dt.timedelta(days=1)
    else:
        d = to_date(day)
        ensure_market(d, d)
        got = store.read_range(CM, d, d)
    if got.empty:
        raise NotAvailable(f"no NSE bhavcopy for {d} (holiday, weekend or not yet published)")
    if series:
        got = got[got["series"].isin(list(series))]
    got.index = ist_index(pd.to_datetime(got.pop("date")))
    return got.reset_index().set_index(["date", "symbol"]).sort_index()


def universe(start: DateLike, end: DateLike = None, series: Sequence[str] = ("EQ", "BE")) -> pd.DataFrame:
    """Panel of every stock that traded in the range (includes later-delisted names).

    Useful to avoid survivorship bias. Returns a long frame indexed by (date, symbol).
    """
    s = to_date(start)
    e = to_date(end, today_ist())
    ensure_market(s, e)
    df = store.read_range(CM, s, e, "series IN ({})".format(",".join("?" * len(series))), tuple(series))
    df.index = ist_index(pd.to_datetime(df.pop("date")))
    return df.reset_index().set_index(["date", "symbol"]).sort_index()

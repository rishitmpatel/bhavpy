"""Date helpers. All public dates in bhavpy are Asia/Kolkata (IST) aware."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Union

import pandas as pd

IST = "Asia/Kolkata"

DateLike = Union[str, dt.date, dt.datetime, pd.Timestamp, None]  # noqa: UP007 (runtime alias, py3.10)


def to_date(value: DateLike, default: dt.date | None = None) -> dt.date:
    """Turn a string/date/datetime/Timestamp into a plain ``datetime.date``."""
    if value is None:
        if default is None:
            raise ValueError("a date is required")
        return default
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if text.lower() == "today":
        return today_ist()
    ts = pd.Timestamp(text)
    return ts.date()


def today_ist() -> dt.date:
    """Today's date in India."""
    return pd.Timestamp.now(tz=IST).date()


def now_ist() -> pd.Timestamp:
    return pd.Timestamp.now(tz=IST)


def ist_index(dates: Iterable[dt.date] | pd.Series | pd.Index, name: str = "date") -> pd.DatetimeIndex:
    """Build a tz-aware (IST, midnight) DatetimeIndex from dates."""
    idx = pd.DatetimeIndex(
        pd.to_datetime(list(dates) if not isinstance(dates, (pd.Series, pd.Index)) else dates)
    )
    idx = idx.tz_localize(IST) if idx.tz is None else idx.tz_convert(IST)
    return idx.rename(name)


def date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    n = (end - start).days
    return [start + dt.timedelta(days=i) for i in range(n + 1)]


def parse_nse_date(text: str) -> dt.date:
    """Parse NSE's date spellings: 19-Oct-2026, 19-OCT-2026, 2026-10-19, 19-10-2026, 15-Apr-02."""
    t = text.strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%y", "%d/%m/%Y", "%d %b %Y", "%d-%B-%Y"):
        try:
            return dt.datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {text!r}")

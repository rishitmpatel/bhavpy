"""NSE trading calendar: holidays, special sessions (Muhurat, Budget-day, DR drills), expiries.

Sources, in order of trust:

1. NSE ``holiday-master`` API (2011 onwards, incl. future scheduled holidays), cached.
2. A bundled calendar (``data/nse_calendar.csv``) built from the API plus the bhavcopy
   archive itself: a weekday with no bhavcopy is a closure, a weekend/holiday with one is
   a special session. This covers 2005 onwards and works offline.
3. Days the cache has seen (a settled 404 for a weekday = closure).
"""

from __future__ import annotations

import datetime as dt
import functools
from importlib import resources

import pandas as pd

from . import cache, http
from .config import settings
from .dates import DateLike, date_range, ist_index, to_date, today_ist
from .errors import BhavpyError
from .sources import nse_holidays

#: Holidays whose evening still has a Muhurat trading session (bhavcopy exists).
_MUHURAT_WORDS = ("laxmi", "lakshmi")


@functools.lru_cache(maxsize=1)
def _bundled() -> pd.DataFrame:
    with resources.files("bhavpy.data").joinpath("nse_calendar.csv").open("r", encoding="utf-8") as fh:
        df = pd.read_csv(fh, dtype=str, keep_default_na=False)
    return df


def _api_holidays(year: int) -> pd.DataFrame:
    key = f"nse_holidays:{year}"
    current = year >= today_ist().year
    raw = cache.cached_blob(
        key,
        lambda: http.get(nse_holidays.URL, expect="json", params=nse_holidays.params(year)),
        max_age_hours=settings.ttl_hours * 7 if current else None,
    )
    return nse_holidays.parse(raw)


def holidays(year: int | None = None, *, include_weekends: bool = False) -> pd.DataFrame:
    """Equity-segment holidays for ``year`` (default: this year).

    Columns: ``description``, ``weekday``, ``muhurat_session`` (True when a special
    evening session was/will be held), ``source``. Index: IST date.
    """
    year = year or today_ist().year
    frames = []
    try:
        api = _api_holidays(year)
        if not api.empty:
            frames.append(api.assign(source="nse_api")[["date", "description", "source"]])
    except BhavpyError:
        pass
    b = _bundled()
    b = b[(b["kind"] == "holiday") & b["date"].str.startswith(str(year))]
    frames.append(b.assign(source="bundled")[["date", "description", "source"]])
    df = pd.concat(frames, ignore_index=True).drop_duplicates("date", keep="first")
    df = df.sort_values("date")
    d = pd.to_datetime(df["date"])
    if not include_weekends:
        df = df[d.dt.weekday < 5]
        d = pd.to_datetime(df["date"])
    sessions = set(special_sessions()["date"].dt.strftime("%Y-%m-%d"))
    out = pd.DataFrame(
        {
            "description": df["description"].to_numpy(),
            "weekday": d.dt.day_name().to_numpy(),
            "muhurat_session": df["date"].isin(sessions).to_numpy()
            | df["description"].str.lower().str.contains("|".join(_MUHURAT_WORDS)).to_numpy(),
            "source": df["source"].to_numpy(),
        },
        index=ist_index(d.dt.date.tolist()),
    )
    return out


def special_sessions() -> pd.DataFrame:
    """Known sessions held on weekends or holidays (Muhurat, Budget day, DR drills)."""
    b = _bundled()
    b = b[b["kind"] == "special_session"]
    return pd.DataFrame(
        {
            "date": pd.to_datetime(b["date"]).dt.tz_localize("Asia/Kolkata"),
            "description": b["description"],
        }
    ).reset_index(drop=True)


def _closed_days(start: dt.date, end: dt.date) -> set[dt.date]:
    closed: set[dt.date] = set()
    for y in range(start.year, end.year + 1):
        for ts in holidays(y).index:
            closed.add(ts.date())
    seen = cache.fetched_days("nse_cm", start, end)
    closed |= {d for d, s in seen.items() if s == "missing"}
    return closed


def _special(start: dt.date, end: dt.date) -> set[dt.date]:
    return {ts.date() for ts in special_sessions()["date"] if start <= ts.date() <= end}


def trading_days(start: DateLike, end: DateLike = None) -> pd.DatetimeIndex:
    """Regular trading days (weekdays that are not holidays) plus known special sessions."""
    s = to_date(start)
    e = to_date(end, today_ist())
    closed = _closed_days(s, e)
    days = [d for d in date_range(s, e) if d.weekday() < 5 and d not in closed]
    days = sorted(set(days) | _special(s, e))
    return ist_index(days)


def candidate_days(start: dt.date, end: dt.date) -> list[dt.date]:
    """Days worth asking the archive for: trading days plus Muhurat-holiday evenings."""
    days = {ts.date() for ts in trading_days(start, end)}
    for y in range(start.year, end.year + 1):
        h = holidays(y)
        days |= {
            ts.date()
            for ts, m in zip(h.index, h["muhurat_session"], strict=False)
            if m and start <= ts.date() <= end
        }
    return sorted(days)


def is_trading_day(day: DateLike = None) -> bool:
    d = to_date(day, today_ist())
    return len(trading_days(d, d)) == 1


def previous_trading_day(day: DateLike = None) -> pd.Timestamp:
    d = to_date(day, today_ist())
    days = trading_days(d - dt.timedelta(days=20), d - dt.timedelta(days=1))
    return days[-1]


def next_trading_day(day: DateLike = None) -> pd.Timestamp:
    d = to_date(day, today_ist())
    days = trading_days(d + dt.timedelta(days=1), d + dt.timedelta(days=20))
    return days[0]

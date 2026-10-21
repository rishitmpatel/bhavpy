"""Download-and-cache engine for daily archive sources.

:func:`ensure` makes sure every trading day in a range is either in the cache or known
to be missing upstream. Only days the fetch log has not settled are downloaded, which is
what makes ``bhavpy update`` incremental.
"""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import logging
import sys
import time

import pandas as pd

from . import cache, http
from .config import settings
from .dates import now_ist, today_ist
from .errors import BhavpyError, BlockedError, FormatChanged, NetworkError, NotAvailable
from .sources.base import DailySource

log = logging.getLogger("bhavpy")

#: A day with no file this many days later is treated as permanently missing (holiday).
SETTLE_DAYS = 3


def _is_settled_missing(day: dt.date) -> bool:
    """True when a 404 for ``day`` can be trusted to be permanent."""
    age = (today_ist() - day).days
    return age >= SETTLE_DAYS


def fetch_day(source: DailySource, day: dt.date) -> pd.DataFrame:
    """Download and parse one day; raises NotAvailable when no candidate URL has it."""
    last: Exception | None = None
    for url in source.urls(day):
        try:
            raw = http.get(url, expect=source.expect_for(url))
        except NotAvailable as exc:
            last = exc
            continue
        try:
            return source.parse(raw, day)
        except NotAvailable as exc:
            last = exc
            continue
        except FormatChanged as exc:
            raise FormatChanged(f"{source.dataset} {day}: {exc} (url: {url})") from exc
    raise NotAvailable(f"{source.dataset}: no file for {day}") from last


def _store(source: DailySource, day: dt.date, df: pd.DataFrame) -> int:
    cache.ensure_table(source.table, source.ddl)
    df = df.copy()
    if "date" not in df or df["date"].isna().all():
        df["date"] = day.isoformat()
    n = cache.write_frame(source.table, source.for_storage(df), source.columns)
    cache.log_fetch(source.dataset, day, "ok", n)
    return n


class _Progress:
    """One self-updating line on a terminal; a line every 10% elsewhere (CI, logs)."""

    def __init__(self, label: str, total: int) -> None:
        self.label, self.total, self.done, self.t0 = label, total, 0, time.monotonic()
        self.enabled = settings.progress and total > 3 and sys.stderr is not None
        self.tty = self.enabled and sys.stderr.isatty()
        self.next_pct = 10

    def step(self) -> None:
        self.done += 1
        if not self.enabled:
            return
        rate = self.done / max(time.monotonic() - self.t0, 1e-6)
        eta = (self.total - self.done) / max(rate, 1e-6)
        msg = f"[bhavpy] {self.label}: {self.done}/{self.total} days (~{eta:0.0f}s left)"
        if self.tty:
            if self.done == self.total or self.done % 5 == 0:
                end = "\n" if self.done == self.total else ""
                sys.stderr.write(f"\r{msg} {end}")
                sys.stderr.flush()
        elif self.done * 100 >= self.next_pct * self.total:
            sys.stderr.write(msg + "\n")
            self.next_pct += 10


def ensure(source: DailySource, days: list[dt.date]) -> dict[str, int]:
    """Fetch the given candidate days that are not yet settled in the cache.

    Returns counts ``{"fetched", "missing", "pending", "failed"}``. Raises
    :class:`BlockedError` / :class:`FormatChanged` immediately (after saving what was
    already downloaded) because continuing would only hammer the server or store junk.
    """
    cache.ensure_table(source.table, source.ddl)
    today = today_ist()
    days = sorted(d for d in set(days) if source.first_date <= d <= today)
    stats = {"fetched": 0, "missing": 0, "pending": 0, "failed": 0}
    if not days:
        return stats
    settled = cache.fetched_days(source.dataset, days[0], days[-1])
    todo = [d for d in days if d not in settled]
    # Today's file appears in the evening; don't ask before ~18:30 IST.
    if todo and todo[-1] == today and now_ist().hour * 60 + now_ist().minute < 18 * 60 + 30:
        todo.pop()
        stats["pending"] += 1
    if not todo or settings.offline:
        stats["pending"] += len(todo)
        return stats

    progress = _Progress(source.dataset, len(todo))
    fatal: BhavpyError | None = None
    with cf.ThreadPoolExecutor(max_workers=max(1, settings.workers)) as pool:
        futures = {pool.submit(fetch_day, source, d): d for d in todo}
        for fut in cf.as_completed(futures):
            day = futures[fut]
            progress.step()
            try:
                df = fut.result()
            except NotAvailable:
                if _is_settled_missing(day):
                    cache.log_fetch(source.dataset, day, "missing")
                    stats["missing"] += 1
                else:
                    stats["pending"] += 1
                continue
            except (BlockedError, FormatChanged) as exc:
                fatal = fatal or exc
                for f in futures:
                    f.cancel()
                continue
            except NetworkError as exc:
                log.warning("%s", exc)
                stats["failed"] += 1
                continue
            _store(source, day, df)
            stats["fetched"] += 1
    if fatal is not None:
        raise fatal
    if stats["failed"]:
        log.warning("%s: %d day(s) failed to download; run again to retry", source.dataset, stats["failed"])
    return stats


def read_range(
    source: DailySource,
    start: dt.date,
    end: dt.date,
    where: str = "",
    params: tuple[object, ...] = (),
) -> pd.DataFrame:
    cache.ensure_table(source.table, source.ddl)
    sql = f"SELECT * FROM {source.table} WHERE date BETWEEN ? AND ?"
    if where:
        sql += f" AND ({where})"
    df = cache.query(sql + " ORDER BY date", (source.date_key(start), source.date_key(end), *params))
    return source.from_storage(df)

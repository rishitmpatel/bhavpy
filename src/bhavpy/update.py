"""``bhavpy update``: bring the cache up to date incrementally."""

from __future__ import annotations

import datetime as dt
import logging

from . import cache, equity, flows, indices, symbols
from .dates import DateLike, to_date, today_ist
from .errors import BhavpyError

log = logging.getLogger("bhavpy")

#: Indices whose constituent lists are snapshotted on every update.
SNAPSHOT_INDICES = (
    "NIFTY 50",
    "NIFTY NEXT 50",
    "NIFTY 100",
    "NIFTY 200",
    "NIFTY 500",
    "NIFTY BANK",
)


def update(start: DateLike = None, *, indices_only: bool = False) -> dict[str, object]:
    """Fetch every missing day since the last cached day (or since ``start``).

    Updates: NSE equity bhavcopies, NSE index closes, FII/DII flows, symbol lists and
    constituent snapshots. Returns a summary dict. Safe to run repeatedly (e.g. daily
    from cron or a scheduled GitHub Action): settled days are never re-downloaded.
    """
    today = today_ist()
    report: dict[str, object] = {}
    last_cm = cache.last_day("nse_cm")
    s_cm = to_date(start) if start is not None else (last_cm or today - dt.timedelta(days=7))
    if not indices_only:
        report["nse_cm"] = equity.ensure_market(s_cm, today)
    last_idx = cache.last_day("nse_index")
    s_idx = to_date(start) if start is not None else (last_idx or today - dt.timedelta(days=7))
    report["nse_index"] = equity.ensure_indices(s_idx, today)
    for name, fn in (
        ("fii_dii", flows.fii_dii),
        ("symbols", symbols.equity_list),
        ("symbol_changes", symbols.symbol_changes),
    ):
        try:
            fn()
            report[name] = "ok"
        except BhavpyError as exc:
            report[name] = f"failed: {exc}"
    snaps: dict[str, object] = {}
    for idx in SNAPSHOT_INDICES:
        try:
            snaps[idx] = len(indices.constituents(idx))
        except BhavpyError as exc:
            snaps[idx] = f"failed: {exc}"
    report["constituents"] = snaps
    return report

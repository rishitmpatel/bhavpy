"""Corporate-action adjustment: the factors, where they came from, and whether prices agree.

How it works
------------
1. Corporate actions come from NSE's own corporate-actions feed (cached), parsed by
   :func:`bhavpy.sources.nse_corpactions.parse_subject`.
2. Each event becomes a *price factor* applied to every price **before** its ex-date:

   ============== ========================================= ===========================
   action         factor                                    example
   ============== ========================================= ===========================
   split          new FV / old FV                           FV 10 -> 2 : 0.2
   consolidation  new FV / old FV                           FV 1 -> 10 : 10
   bonus a:b      b / (a + b)                               1:1 : 0.5
   rights a:b @S  TERP / P, TERP = (b*P + a*S) / (a + b)    only when S < P
   dividend D     (P - D) / P   (``adjust="total"`` only)   CRSP-style total return
   ============== ========================================= ===========================

   ``P`` is the last close before the ex-date (the cum price).
3. **Price check.** For splits, bonuses and consolidations the overnight move
   ``open(ex) / P`` must be within 25% of the factor. If the market says otherwise the
   record is reported with ``check="mismatch"`` and not applied (configurable).
4. **Gap scan.** Overnight jumps that look like a split/bonus but have no matching record
   are reported as ``unexplained_gap`` (and applied only with ``infer=True``, or
   automatically when the corporate-action feed is unreachable).

The output of :func:`factors` shows every event, its factor, its source and its check,
so the adjustment is fully auditable.
"""

from __future__ import annotations

import logging
import math
import warnings

import numpy as np
import pandas as pd

from . import cache, http, symbols
from .config import settings
from .dates import today_ist
from .errors import BhavpyError
from .sources import nse_corpactions as ca_src

log = logging.getLogger("bhavpy")

_CA_DDL = """
CREATE TABLE IF NOT EXISTS corp_actions (
    symbol TEXT NOT NULL, series TEXT, isin TEXT, company TEXT, ex_date TEXT NOT NULL,
    record_date TEXT, face_value REAL, subject TEXT NOT NULL,
    PRIMARY KEY (symbol, ex_date, subject)
) WITHOUT ROWID;
"""

#: Series whose corporate actions affect the ordinary share price.
_EQUITY_SERIES = {"EQ", "BE", "BZ", "BT", "SM", "ST", "SZ", "E1", ""}

EVENT_COLUMNS = [
    "ex_date", "kind", "ratio", "amount", "price_factor", "volume_factor", "applied",
    "check", "source", "description",
]  # fmt: skip

#: Tolerance for the price check of split/bonus factors.
CHECK_TOLERANCE = 0.25


# --------------------------------------------------------------------------- data


def _fetch_actions(symbol: str, refresh: bool) -> bool:
    """Make sure corp actions for one ticker are cached. Returns False if the feed failed."""
    key = f"corp_actions_fetched:{symbol}"
    if not refresh and cache.blob_get(key, settings.ttl_hours) is not None:
        return True
    if settings.offline:
        return cache.blob_get(key) is not None
    try:
        raw = http.get(
            ca_src.URL,
            expect="json",
            params=ca_src.params(symbol, "01-01-1995", today_ist().strftime("%d-%m-%Y")),
        )
        df = ca_src.parse(raw)
    except BhavpyError as exc:
        log.warning("corporate actions for %s unavailable: %s", symbol, exc)
        return cache.blob_get(key) is not None
    cache.ensure_table("corp_actions", _CA_DDL)
    if not df.empty:
        cache.write_frame("corp_actions", df, ca_src.COLUMNS)
    cache.blob_put(key, b"1")
    return True


def corporate_actions(symbol: str, *, refresh: bool = False) -> pd.DataFrame:
    """Raw NSE corporate-action records for ``symbol`` and all its former tickers."""
    cache.ensure_table("corp_actions", _CA_DDL)
    chain = symbols.symbol_chain(symbol)
    ok = True
    frames = []
    for seg in chain:
        ok &= _fetch_actions(seg.symbol, refresh)
        rows = cache.query("SELECT * FROM corp_actions WHERE symbol = ?", (seg.symbol,))
        # A ticker can be reused by another company later: keep only records from the
        # window in which this security used it (an ex-date on the rename day may be
        # filed under either ticker, so both ends are inclusive).
        if seg.start is not None:
            rows = rows[rows["ex_date"] >= seg.start.isoformat()]
        if seg.end is not None:
            rows = rows[rows["ex_date"] <= seg.end.isoformat()]
        frames.append(rows)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=list(ca_src.COLUMNS))
    df = df[df["series"].fillna("").isin(_EQUITY_SERIES)]
    df = df.drop_duplicates(subset=["ex_date", "subject"]).sort_values("ex_date").reset_index(drop=True)
    df.attrs["feed_ok"] = bool(ok)
    return df


# --------------------------------------------------------------------------- factors


def _ratio_text(ev: ca_src.Event) -> str:
    if ev.kind in ("split", "consolidation"):
        return f"FV {ev.a:g}->{ev.b:g}"
    if ev.kind in ("bonus", "rights"):
        return f"{ev.a:g}:{ev.b:g}"
    return ""


def _cum_close(prices: pd.DataFrame, ex: pd.Timestamp) -> tuple[float | None, float | None]:
    """(last close before ex, first open on/after ex)."""
    before = prices.loc[prices.index < ex, "close"].dropna()
    after = prices.loc[prices.index >= ex]
    p = float(before.iloc[-1]) if len(before) else None
    o = None
    if len(after):
        row = after.iloc[0]
        o = float(row["open"]) if pd.notna(row.get("open")) and row.get("open") else float(row["close"])
    return p, o


def _candidate_ratios() -> np.ndarray:
    vals = {b / (a + b) for a in range(1, 11) for b in range(1, 11)}
    vals |= {new / old for old in (10, 5, 2, 1) for new in (5, 2, 1, 0.5, 0.25) if new < old}
    vals |= {1 / v for v in list(vals)}
    return np.array(sorted(v for v in vals if not 0.85 < v < 1.18))


_CANDIDATES = _candidate_ratios()


def build_events(
    actions: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    mode: str = "split",
    infer: bool | None = None,
    on_mismatch: str = "skip",
    demerger: str = "ignore",
) -> pd.DataFrame:
    """Turn corporate-action records + raw prices into an auditable factor table.

    ``prices`` is a raw daily frame indexed by IST date with ``open`` and ``close``.
    ``mode``: ``"split"`` (splits, bonuses, rights) or ``"total"`` (also dividends).
    ``infer``: apply split-like price gaps with no record (None = only if feed failed).
    ``on_mismatch``: ``"skip"`` or ``"apply"`` records the price check contradicts.
    ``demerger``: ``"ignore"`` or ``"estimate"`` (factor = ex-day open / cum close).
    """
    tz = prices.index.tz if isinstance(prices.index, pd.DatetimeIndex) else None
    rows: list[dict[str, object]] = []
    for rec in actions.to_dict("records"):
        ex = pd.Timestamp(str(rec["ex_date"]))
        ex = ex.tz_localize(tz) if tz is not None else ex
        fv = rec.get("face_value")
        face_value = float(fv) if fv is not None and pd.notna(fv) else None
        for ev in ca_src.parse_subject(str(rec["subject"]), face_value):
            if ev.kind == "dividend" and mode != "total":
                continue
            p, o = _cum_close(prices, ex)
            pf: float | None = None
            vf = 1.0
            check = "ok"
            if ev.kind in ("split", "consolidation"):
                assert ev.a and ev.b
                pf = ev.b / ev.a
                vf = 1 / pf
            elif ev.kind == "bonus":
                assert ev.a and ev.b
                pf = ev.b / (ev.a + ev.b)
                vf = 1 / pf
            elif ev.kind == "rights":
                if ev.amount is None:
                    check = "no_issue_price"
                elif p is None:
                    check = "no_price_data"
                elif ev.amount >= p:
                    pf, check = 1.0, "rights_above_market"
                else:
                    assert ev.a and ev.b
                    terp = (ev.b * p + ev.a * ev.amount) / (ev.a + ev.b)
                    pf = terp / p
            elif ev.kind == "dividend":
                assert ev.amount is not None
                if p is None:
                    check = "no_price_data"
                elif ev.amount >= p:
                    check = "dividend_exceeds_price"
                else:
                    pf = (p - ev.amount) / p
            elif ev.kind in ("demerger", "capital_reduction"):
                if demerger == "estimate" and p and o and 0 < o < p:
                    pf, check = o / p, "estimated"
                else:
                    check = "not_adjusted"
            if pf is not None and ev.kind in ("split", "consolidation", "bonus") and p and o:
                observed = o / p
                if not (1 - CHECK_TOLERANCE) < observed / pf < 1 / (1 - CHECK_TOLERANCE):
                    check = "mismatch"
            elif pf is not None and ev.kind in ("split", "consolidation", "bonus") and not (p and o):
                check = "no_price_data" if (p or o) else "outside_range"
            applied = pf is not None and (
                check in ("ok", "estimated", "no_price_data", "outside_range")
                or (check == "mismatch" and on_mismatch == "apply")
            )
            rows.append(
                {
                    "ex_date": ex,
                    "kind": ev.kind,
                    "ratio": _ratio_text(ev),
                    "amount": ev.amount,
                    "price_factor": pf if pf is not None else 1.0,
                    "volume_factor": vf if applied else 1.0,
                    "applied": applied,
                    "check": check,
                    "source": "nse_corporate_actions",
                    "description": str(rec["subject"]),
                }
            )
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    if not events.empty:
        events = events.drop_duplicates(subset=["ex_date", "kind", "ratio", "amount"])

    # Gap scan for split-like moves with no record.
    feed_ok = bool(actions.attrs.get("feed_ok", True))
    apply_inferred = (not feed_ok) if infer is None else infer
    gaps = _scan_gaps(prices, events)
    if not gaps.empty:
        gaps["applied"] = apply_inferred
        gaps.loc[~gaps["applied"], "volume_factor"] = 1.0
        events = pd.concat([events, gaps], ignore_index=True) if not events.empty else gaps
    events = events.sort_values("ex_date").reset_index(drop=True)
    bad = events[events["check"] == "mismatch"]
    if len(bad):
        warnings.warn(
            f"{len(bad)} corporate action(s) contradicted by prices "
            f"({', '.join(bad['ex_date'].dt.strftime('%Y-%m-%d'))}); "
            f"{'applied anyway' if on_mismatch == 'apply' else 'not applied'}. See bhavpy.factors().",
            stacklevel=3,
        )
    return events


def _scan_gaps(prices: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if len(prices) < 2:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    close = prices["close"].astype(float)
    opn = prices["open"].astype(float).where(prices["open"] > 0, close)
    ratio = (opn / close.shift(1)).iloc[1:]
    big = ratio[(ratio < 0.67) | (ratio > 1.5)].dropna()
    known = pd.DatetimeIndex(events["ex_date"]) if not events.empty else pd.DatetimeIndex([])
    rows = []
    for ts, r in big.items():
        if len(known) and (abs((known - ts).days) <= 7).any():
            continue
        cand = _CANDIDATES[np.argmin(np.abs(np.log(_CANDIDATES) - math.log(r)))]
        if abs(math.log(r / cand)) > math.log(1.06):
            continue
        rows.append(
            {
                "ex_date": ts,
                "kind": "unexplained_gap",
                "ratio": f"~{cand:.4g}",
                "amount": None,
                "price_factor": float(cand),
                "volume_factor": float(1 / cand),
                "applied": False,
                "check": "inferred",
                "source": "price_gap",
                "description": f"overnight open/prev close = {r:.4f}, no corporate-action record",
            }
        )
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def cumulative(index: pd.DatetimeIndex, events: pd.DataFrame, column: str = "price_factor") -> pd.Series:
    """Product of factors of applied events with ex_date strictly after each date."""
    ev = events[events["applied"]] if not events.empty else events
    if ev.empty:
        return pd.Series(1.0, index=index)
    ev = ev.groupby("ex_date")[column].prod().sort_index()
    # suffix products: factor for dates before ex_k = prod(f_j for j >= k)
    suffix = np.cumprod(ev.to_numpy()[::-1])[::-1]
    pos = np.searchsorted(ev.index.to_numpy(), index.to_numpy(), side="right")
    vals = np.append(suffix, 1.0)[pos]
    return pd.Series(vals, index=index)


def apply(prices: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Add adj_open/high/low/close/volume and adj_factor columns to a raw price frame."""
    out = prices.copy()
    pf = cumulative(out.index, events, "price_factor")
    vf = cumulative(out.index, events, "volume_factor")
    for col in ("open", "high", "low", "close", "last", "prev_close"):
        if col in out:
            out[f"adj_{col}"] = out[col] * pf
    if "prev_close" in out:
        # prev_close on the ex-date itself is the cum price; rebase it with that day's factor too
        ex_days = events.loc[events["applied"], "ex_date"] if not events.empty else []
        mask = out.index.isin(pd.DatetimeIndex(ex_days))
        if mask.any():
            day_pf = events[events["applied"]].groupby("ex_date")["price_factor"].prod()
            out.loc[mask, "adj_prev_close"] = (
                out.loc[mask, "adj_prev_close"] * day_pf.reindex(out.index[mask]).to_numpy()
            )
    if "volume" in out:
        out["adj_volume"] = out["volume"] * vf
    out["adj_factor"] = pf
    return out

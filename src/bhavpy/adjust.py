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

#: Actions that change the share count (price-checked, volumes rescaled).
_SHARE_KINDS = ("split", "consolidation", "bonus")


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
        # NSE files a security's whole history under its *current* ticker, but an old
        # ticker may later be reused by another company: drop records of a former
        # ticker dated after this security stopped using it.
        if seg.end is not None and seg is not chain[-1]:
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


def _cum_close(prices: pd.DataFrame, ex: pd.Timestamp) -> tuple[float | None, float | None, float | None]:
    """(last close before ex, first open on/after ex, first close on/after ex)."""
    before = prices.loc[prices.index < ex, "close"].dropna()
    after = prices.loc[prices.index >= ex]
    p = float(before.iloc[-1]) if len(before) else None
    o = c = None
    if len(after):
        row = after.iloc[0]
        c = float(row["close"])
        o = float(row["open"]) if pd.notna(row.get("open")) and row.get("open") else c
    return p, o, c


def _demerger_factor(p: float | None, o: float | None, c: float | None) -> float | None:
    """Estimate the value left in the parent after a demerger.

    Since ~2018 NSE runs a special pre-open session on the ex-date, so the ex-day open is
    the discovered parent price (RELIANCE 2023-07-20 opened at 2,580 after JIO FIN).
    Older ex-dates sometimes opened at the stale price and fell during the day; when the
    close is >25% away from the open, the close is the better estimate.
    """
    if not (p and o and c):
        return None
    est = c if abs(math.log(c / o)) > math.log(1.25) else o
    return est / p if 0 < est < p else None


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
    demerger: str = "estimate",
) -> pd.DataFrame:
    """Turn corporate-action records + raw prices into an auditable factor table.

    ``prices`` is a raw daily frame indexed by IST date with ``open`` and ``close``.
    ``mode``: ``"split"`` (splits, bonuses, rights) or ``"total"`` (also dividends).
    ``infer``: apply split-like price gaps with no record (None = only if feed failed).
    ``on_mismatch``: ``"skip"`` or ``"apply"`` records the price check contradicts.
    ``demerger``: ``"estimate"`` (default; see :func:`_demerger_factor`) or ``"ignore"``.
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
            p, o, c = _cum_close(prices, ex)
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
            elif ev.kind in ("demerger", "scheme_of_arrangement", "capital_reduction"):
                est = _demerger_factor(p, o, c) if demerger == "estimate" else None
                if est is not None:
                    pf, check = est, "estimated"
                else:
                    check = "not_adjusted"
            if pf is not None and ev.kind in _SHARE_KINDS and not (p and o):
                check = "no_price_data" if (p or o) else "outside_range"
            rows.append(
                {
                    "ex_date": ex,
                    "kind": ev.kind,
                    "ratio": _ratio_text(ev),
                    "amount": ev.amount,
                    "price_factor": pf if pf is not None else 1.0,
                    "volume_factor": vf,
                    "applied": pf is not None,
                    "check": check,
                    "source": "nse_corporate_actions",
                    "description": str(rec["subject"]),
                    "_observed": (o / p) if (p and o) else np.nan,
                }
            )
    events = pd.DataFrame(rows, columns=[*EVENT_COLUMNS, "_observed"])
    if not events.empty:
        events = events.drop_duplicates(subset=["ex_date", "kind", "ratio", "amount"])
        # Price check per ex-date on the *combined* share-count factor (a split and a
        # bonus often share an ex-date, e.g. BAJFINANCE 2016-09-08 and 2025-06-16).
        share = events[events["kind"].isin(_SHARE_KINDS) & events["applied"]]
        for _, grp in share.groupby("ex_date"):
            observed = grp["_observed"].iloc[0]
            if pd.isna(observed):
                continue
            ratio = observed / grp["price_factor"].prod()
            if not (1 - CHECK_TOLERANCE) < ratio < 1 / (1 - CHECK_TOLERANCE):
                events.loc[grp.index, "check"] = "mismatch"
        ok = events["check"].isin(["ok", "estimated", "no_price_data", "outside_range"])
        if on_mismatch == "apply":
            ok |= events["check"] == "mismatch"
        events["applied"] = events["applied"] & ok
        events.loc[~events["applied"], "volume_factor"] = 1.0
    events = events.drop(columns="_observed")

    # Gap scan for split-like moves with no record.
    feed_ok = bool(actions.attrs.get("feed_ok", True))
    apply_inferred = (not feed_ok) if infer is None else infer
    gaps = _scan_gaps(prices, events)
    if not gaps.empty:
        gaps["applied"] = apply_inferred & (gaps["check"] == "inferred")
        gaps.loc[~gaps["applied"], "volume_factor"] = 1.0
        events = pd.concat([events, gaps], ignore_index=True) if not events.empty else gaps
    events = events.sort_values("ex_date").reset_index(drop=True)
    events["applied"] = events["applied"].astype(bool)
    events["ex_date"] = pd.to_datetime(events["ex_date"], utc=True).dt.tz_convert(tz or "Asia/Kolkata")
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
    big = ratio[(ratio < 0.77) | (ratio > 1.3)].dropna()
    known = pd.DatetimeIndex(events["ex_date"]) if not events.empty else pd.DatetimeIndex([])
    rows = []
    for ts, r in big.items():
        if len(known) and (abs((known - ts).days) <= 7).any():
            continue
        cand = _CANDIDATES[np.argmin(np.abs(np.log(_CANDIDATES) - math.log(r)))]
        if abs(math.log(r / cand)) > math.log(1.06):
            if abs(math.log(r)) > math.log(1.5):
                # Too big for normal trading and not a split/bonus ratio: likely an
                # unrecorded demerger or scheme. Reported, never applied.
                rows.append(
                    {
                        "ex_date": ts,
                        "kind": "unexplained_gap",
                        "ratio": "?",
                        "amount": None,
                        "price_factor": float(r),
                        "volume_factor": 1.0,
                        "applied": False,
                        "check": "unknown_ratio",
                        "source": "price_gap",
                        "description": f"overnight open/prev close = {r:.4f}; no record, no standard ratio",
                    }
                )
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

"""Symbol master: current listings, ISINs, symbol/name changes, delistings.

Old tickers keep working: ``bhavpy.history("ZOMATO")`` resolves to ``ETERNAL`` and
stitches both symbols' history together, using NSE's own symbol-change file.
"""

from __future__ import annotations

import datetime as dt
import functools
from dataclasses import dataclass

import pandas as pd

from . import cache, http
from .config import settings
from .errors import BhavpyError, SymbolNotFound
from .sources import nse_symbols


def _snapshot(name: str) -> bytes:
    url = nse_symbols.URLS[name]
    return cache.cached_blob(f"nse_symbols:{name}", lambda: http.get(url, expect="csv"), settings.ttl_hours)


def equity_list(include_sme: bool = True) -> pd.DataFrame:
    """Currently listed NSE equities: symbol, name, series, listing_date, isin, face_value, board."""
    frames = [nse_symbols.parse_equity_list(_snapshot("equity_list"), "main")]
    if include_sme:
        try:
            frames.append(nse_symbols.parse_equity_list(_snapshot("sme_list"), "sme"))
        except BhavpyError:
            pass
    return pd.concat(frames, ignore_index=True)


def symbol_changes() -> pd.DataFrame:
    """Every NSE symbol change: old_symbol, new_symbol, effective_date, name."""
    return nse_symbols.parse_symbol_changes(_snapshot("symbol_changes"))


def name_changes() -> pd.DataFrame:
    return nse_symbols.parse_name_changes(_snapshot("name_changes"))


def delisted() -> pd.DataFrame:
    return nse_symbols.parse_delisted(_snapshot("delisted"))


@dataclass(frozen=True)
class Segment:
    """``symbol`` was the ticker from ``start`` (inclusive) to ``end`` (exclusive); None = open."""

    symbol: str
    start: dt.date | None
    end: dt.date | None


def _norm(symbol: str) -> str:
    return symbol.strip().upper().removesuffix(".NS").removesuffix("-EQ")


def chain_from(symbol: str, changes: pd.DataFrame, listed: set[str]) -> list[Segment]:
    """Pure function behind :func:`symbol_chain` (testable without network)."""
    s = _norm(symbol)
    ch = changes.assign(
        old_symbol=changes["old_symbol"].str.upper(),
        new_symbol=changes["new_symbol"].str.upper(),
        eff=pd.to_datetime(changes["effective_date"]).dt.date,
    )
    # Walk forward to today's symbol (unless the given one is listed today).
    cur, t = s, dt.date.min
    if s not in listed:
        for _ in range(25):
            nxt = ch[(ch["old_symbol"] == cur) & (ch["eff"] > t)].sort_values("eff")
            if nxt.empty:
                break
            row = nxt.iloc[0]
            cur, t = row["new_symbol"], row["eff"]
            if cur in listed:
                break
    # Walk backward from today's symbol.
    segments: list[Segment] = []
    sym, end_bound = cur, None
    seen: set[tuple[str, dt.date | None]] = set()
    for _ in range(25):
        cond = ch["new_symbol"] == sym
        if end_bound is not None:
            cond &= ch["eff"] < end_bound
        prev = ch[cond].sort_values("eff")
        if prev.empty:
            segments.append(Segment(sym, None, end_bound))
            break
        row = prev.iloc[-1]
        if (row["old_symbol"], row["eff"]) in seen or row["old_symbol"] == sym:
            segments.append(Segment(sym, row["eff"], end_bound))
            break
        seen.add((row["old_symbol"], row["eff"]))
        segments.append(Segment(sym, row["eff"], end_bound))
        sym, end_bound = row["old_symbol"], row["eff"]
    return list(reversed(segments))


@functools.lru_cache(maxsize=4096)
def _chain_cached(symbol: str, stamp: int) -> tuple[Segment, ...]:
    try:
        changes = symbol_changes()
    except BhavpyError:
        return (Segment(_norm(symbol), None, None),)
    try:
        listed = set(equity_list()["symbol"].str.upper())
    except BhavpyError:
        listed = set()
    return tuple(chain_from(symbol, changes, listed))


def symbol_chain(symbol: str) -> list[Segment]:
    """All tickers this security traded under, oldest first, with validity windows."""
    stamp = int(dt.datetime.now().timestamp() // 3600)
    return list(_chain_cached(_norm(symbol), stamp))


def resolve(symbol: str) -> str:
    """Today's ticker for ``symbol`` (follows NSE symbol changes)."""
    return symbol_chain(symbol)[-1].symbol


def info(symbol: str) -> dict[str, object]:
    """Listing details plus history for a symbol (current or old)."""
    chain = symbol_chain(symbol)
    current = chain[-1].symbol
    eq = equity_list()
    row = eq[eq["symbol"].str.upper() == current]
    out: dict[str, object] = {
        "symbol": current,
        "listed": not row.empty,
        "history": [s.__dict__ for s in chain],
    }
    if not row.empty:
        out.update(row.iloc[0].to_dict())
    else:
        dl = delisted()
        hit = dl[dl["symbol"].str.upper() == current]
        if not hit.empty:
            out.update({"delisted_date": hit.iloc[0]["delisted_date"], "reason": hit.iloc[0]["reason"]})
        elif len(chain) == 1:
            raise SymbolNotFound(f"{symbol!r} is not listed, renamed or delisted on NSE")
    return out

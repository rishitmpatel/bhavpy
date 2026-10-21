"""Live checks against the real NSE/BSE servers.

Run with ``pytest -m live tests/live``. The scheduled GitHub Action runs this every
day and opens (or updates) an issue when any source changes its URL or format, so
breakages are caught within a day instead of when users hit them.

Every test uses a fresh temporary cache and asks for something small.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

import bhavpy as bp
from bhavpy import cache, store
from bhavpy.dates import today_ist
from bhavpy.equity import CM, INDEX
from bhavpy.fno import FO
from bhavpy.sources.bse_cm import BseCmBhavcopy

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def fresh_cache(tmp_path: Path) -> Iterator[None]:
    old = bp.settings.cache_dir
    bp.configure(cache_dir=tmp_path, progress=False, offline=False, rate=2)
    yield
    cache.reset()
    bp.configure(cache_dir=old)


def recent_trading_day() -> dt.date:
    """Most recent day that should already have published end-of-day files."""
    d = today_ist() - dt.timedelta(days=1)
    for _ in range(10):
        if bp.is_trading_day(d):
            return d
        d -= dt.timedelta(days=1)
    raise AssertionError("no trading day in the last 10 days?")


def _latest(source: object) -> pd.DataFrame:
    d = recent_trading_day()
    for _ in range(5):
        try:
            return store.fetch_day(source, d)  # type: ignore[arg-type]
        except bp.NotAvailable:
            d -= dt.timedelta(days=1)
    name = source.__class__.__name__
    raise AssertionError(f"{name}: nothing published in the 5 days up to {recent_trading_day()}")


def test_nse_cm_udiff_bhavcopy() -> None:
    df = _latest(CM)
    assert len(df) > 1500 and df["close"].gt(0).mean() > 0.99
    assert {"RELIANCE", "TCS", "HDFCBANK"} <= set(df["symbol"])


def test_nse_cm_legacy_archive() -> None:
    df = store.fetch_day(CM, dt.date(2017, 9, 7))
    rel = df[(df["symbol"] == "RELIANCE") & (df["series"] == "EQ")]
    assert rel["close"].iloc[0] == pytest.approx(818.10)


def test_nse_fo_bhavcopy() -> None:
    df = _latest(FO)
    assert {"FUTIDX", "OPTIDX", "FUTSTK", "OPTSTK"} <= set(df["instrument"])
    assert df["expiry"].notna().all()


def test_nse_index_close() -> None:
    df = _latest(INDEX)
    assert {"NIFTY 50", "NIFTY BANK", "INDIA VIX"} <= set(df["index"])


def test_bse_bhavcopy() -> None:
    df = _latest(BseCmBhavcopy())
    assert len(df) > 2000 and "500325" in set(df["scrip_code"])


def test_symbol_master_files() -> None:
    eq = bp.equity_list()
    assert len(eq) > 2000 and eq["isin"].str.match(r"^IN[A-Z0-9]{10}$").mean() > 0.99
    ch = bp.symbols.symbol_changes()
    assert len(ch) > 500
    assert bp.resolve("ZOMATO") == "ETERNAL"
    assert len(bp.symbols.delisted()) > 100


def test_corporate_actions_feed_and_adjustment() -> None:
    ca = bp.corporate_actions("RELIANCE")
    assert ca.attrs["feed_ok"] and (ca["subject"].str.contains("Bonus")).sum() >= 2
    df = bp.history("RELIANCE", "2024-10-21", "2024-11-04")
    ev = df.attrs["events"]
    assert (ev["kind"] == "bonus").any() and ev["applied"].all()
    jumps = (df["adj_close"] / df["adj_close"].shift()).dropna()
    assert jumps.between(0.9, 1.1).all(), "adjusted series must be continuous across the 1:1 bonus"


def test_holiday_api() -> None:
    h = bp.holidays(today_ist().year)
    assert (h["source"] == "nse_api").any() and len(h) >= 10


def test_constituents_and_nifty50_history() -> None:
    cur = bp.constituents("NIFTY 50")
    assert len(cur) == 50
    past = bp.constituents("NIFTY 50", as_of="2020-01-01")
    assert len(past) == 50
    # every reconstructed member must actually have traded on that date
    traded = set(bp.market("2020-01-01").reset_index()["symbol"])
    missing = [
        s for s in past["symbol"] if not any(seg.symbol in traded for seg in bp.symbols.symbol_chain(s))
    ]
    assert not missing, f"reconstructed NIFTY 50 members with no trade on 2020-01-01: {missing}"
    n500 = bp.constituents("NIFTY 500")
    assert 490 <= len(n500) <= 510


def test_lot_sizes_file() -> None:
    lots = bp.lot_sizes()
    assert (lots["symbol"] == "NIFTY").any() and lots["lot_size"].gt(0).all()


def test_option_chain_live() -> None:
    exp = bp.expiries("NIFTY")
    assert exp and exp[0] >= today_ist()
    chain = bp.option_chain("NIFTY", exp[0])
    assert set(chain["option_type"]) == {"CE", "PE"} and len(chain) > 50
    assert chain.attrs["underlying_price"] > 1000


def test_fii_dii_live() -> None:
    df = bp.fii_dii()
    assert set(df["category"]) == {"FII", "DII"}


def test_deals_history_api() -> None:
    end = recent_trading_day()
    bulk = bp.bulk_deals(end - dt.timedelta(days=14), end)
    assert not bulk.empty and bulk["quantity"].gt(0).all()
    bp.block_deals(end - dt.timedelta(days=30), end)  # may legitimately be empty; must not raise

"""End-to-end through the public API with a fake exchange (recorded files, no network)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

import bhavpy as bp
from bhavpy import cache, cli, store
from bhavpy.equity import CM

from .conftest import FakeServer


def test_history_adjusts_across_legacy_bonus(offline_http: FakeServer) -> None:
    df = bp.history("RELIANCE", "2017-09-06", "2017-09-07")
    assert list(df.index.strftime("%Y-%m-%d")) == ["2017-09-06", "2017-09-07"]
    assert str(df.index.tz) == "Asia/Kolkata"
    assert df["close"].tolist() == pytest.approx([1645.40, 818.10])
    assert df["adj_close"].tolist() == pytest.approx([822.70, 818.10])
    ev = df.attrs["events"]
    assert ev["kind"].tolist() == ["bonus"] and ev["applied"].all()


def test_raw_history_and_cache_is_incremental(offline_http: FakeServer) -> None:
    raw = bp.history("RELIANCE", "2017-09-06", "2017-09-07", adjust=None)
    assert "adj_close" not in raw
    n = len(offline_http.calls)
    bp.history("RELIANCE", "2017-09-06", "2017-09-07", adjust=None)
    archive_calls = [u for u in offline_http.calls[n:] if "historical/EQUITIES" in u]
    assert archive_calls == [], "second call must be served from cache"


def test_missing_old_day_is_logged_as_missing(offline_http: FakeServer) -> None:
    stats = store.ensure(CM, [dt.date(2017, 9, 8)])  # no fixture -> 404
    assert stats["missing"] == 1
    assert cache.fetched_days("nse_cm", dt.date(2017, 9, 8), dt.date(2017, 9, 8)) == {
        dt.date(2017, 9, 8): "missing"
    }
    before = len(offline_http.calls)
    store.ensure(CM, [dt.date(2017, 9, 8)])
    assert len(offline_http.calls) == before


def test_offline_mode_serves_cache_only(offline_http: FakeServer) -> None:
    bp.history("RELIANCE", "2017-09-06", "2017-09-07", adjust=None)
    bp.configure(offline=True)
    try:
        df = bp.history("RELIANCE", "2017-09-06", "2017-09-07", adjust=None)
        assert len(df) == 2
    finally:
        bp.configure(offline=False)


def test_renamed_symbol_history_stitches(offline_http: FakeServer) -> None:
    chain = bp.symbol_chain("ZOMATO")
    assert [s.symbol for s in chain] == ["ZOMATO", "ETERNAL"]
    assert bp.resolve("ZOMATO") == "ETERNAL"


def test_market_and_universe(offline_http: FakeServer) -> None:
    m = bp.market("2026-10-19")
    assert "RELIANCE" in m.index.get_level_values("symbol")
    u = bp.universe("2017-09-06", "2017-09-07")
    assert set(u.index.get_level_values("symbol")) >= {"RELIANCE", "TCS", "INFY"}


def test_index_history(offline_http: FakeServer) -> None:
    df = bp.history("NIFTY 50", "2026-10-19", "2026-10-19")
    assert df["close"].iloc[0] == pytest.approx(22888.95)
    old = bp.index_history("S&P CNX Nifty", "2013-01-02", "2013-01-02")
    assert len(old) == 1


def test_fno_and_live_snapshots(offline_http: FakeServer) -> None:
    fo = bp.fno.bhavcopy("2026-10-19")
    assert {"FUTIDX", "OPTIDX"} <= set(fo["instrument"])
    fut = bp.futures("NIFTY", "2026-10-19", "2026-10-19")
    assert len(fut) == 1
    chain = bp.option_chain("NIFTY")
    assert chain.attrs["underlying_price"] == pytest.approx(22811.35)
    assert bp.expiries("NIFTY")[0] == dt.date(2026, 10, 27)
    assert (bp.lot_sizes()["lot_size"] > 0).all()


def test_flows_constituents_bse(offline_http: FakeServer) -> None:
    f = bp.fii_dii()
    assert set(f["category"]) == {"FII", "DII"}
    hist = bp.fii_dii_history()
    assert "fii_net" in hist.columns
    c = bp.constituents("NIFTY 50")
    assert len(c) == 50
    old = bp.constituents("NIFTY 50", as_of="2019-01-01")
    assert len(old) == 50 and "YESBANK" in set(old["symbol"])
    deals = bp.bulk_deals("2026-10-01", "2026-10-02")
    assert not deals.empty
    b = bp.bse.bhavcopy("2026-10-19")
    assert "500325" in set(b["scrip_code"])
    mp = bp.bse.nse_bse_map("2026-10-19")
    assert mp.set_index("nse_symbol").at["RELIANCE", "bse_code"] == "500325"


def test_cli_download(offline_http: FakeServer, tmp_path: Path) -> None:
    out = tmp_path / "rel.csv"
    code = cli.main(
        [
            "-q",
            "download",
            "RELIANCE",
            "--from",
            "2017-09-06",
            "--to",
            "2017-09-07",
            "--adjusted",
            "-o",
            str(out),
        ]
    )
    assert code == 0
    df = pd.read_csv(out)
    assert df["date"].tolist() == ["2017-09-06", "2017-09-07"]
    assert df["adj_close"].tolist() == pytest.approx([822.70, 818.10])


def test_cli_reports_errors_cleanly(offline_http: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["-q", "download", "NOSUCHSTOCK", "--from", "2017-09-06", "--to", "2017-09-07"])
    assert code == 2
    assert "SymbolNotFound" in capsys.readouterr().err

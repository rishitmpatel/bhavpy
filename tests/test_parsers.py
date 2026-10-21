"""Every source parser against recorded real files (no network)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from bhavpy.errors import FormatChanged, NotAvailable
from bhavpy.sources import (
    bse_cm,
    niftyindices,
    nse_cm,
    nse_deals,
    nse_fiidii,
    nse_fo,
    nse_holidays,
    nse_indices,
    nse_lots,
    nse_options,
    nse_symbols,
)

from .conftest import fixture_bytes


def test_cm_udiff() -> None:
    src = nse_cm.NseCmBhavcopy()
    df = src.parse(fixture_bytes("BhavCopy_NSE_CM_0_0_0_20261019_F_0000.csv.zip"), dt.date(2026, 10, 19))
    assert list(df.columns) == list(nse_cm.COLUMNS)
    assert "SGBJUN28" not in set(df["symbol"]), "gold bonds must be filtered out"
    rel = df[df["symbol"] == "RELIANCE"].iloc[0]
    assert rel["date"] == "2026-10-19"
    assert rel["series"] == "EQ"
    assert rel["isin"] == "INE002A01018"
    assert rel["close"] > 0 and rel["volume"] > 0
    assert {"NIFTYBEES", "ETERNAL", "TMPV"} <= set(df["symbol"])


def test_cm_udiff_all_series() -> None:
    src = nse_cm.NseCmBhavcopy(series=None)
    df = src.parse(fixture_bytes("BhavCopy_NSE_CM_0_0_0_20261019_F_0000.csv.zip"), dt.date(2026, 10, 19))
    assert "SGBJUN28" in set(df["symbol"])


def test_cm_legacy_2017() -> None:
    src = nse_cm.NseCmBhavcopy()
    df = src.parse(fixture_bytes("cm07SEP2017bhav.csv.zip"), dt.date(2017, 9, 7))
    rel = df[(df["symbol"] == "RELIANCE") & (df["series"] == "EQ")].iloc[0]
    assert rel["date"] == "2017-09-07"
    assert rel["close"] == pytest.approx(818.10)
    # NSE does NOT rebase prev_close on the bonus ex-date (documented behaviour).
    assert rel["prev_close"] == pytest.approx(1645.40)
    assert rel["trades"] == 125644


def test_cm_legacy_2000_without_isin_and_trades() -> None:
    df = nse_cm.NseCmBhavcopy().parse(fixture_bytes("cm03JAN2000bhav.csv.zip"), dt.date(2000, 1, 3))
    assert df["date"].unique().tolist() == ["2000-01-03"]
    assert df["isin"].isna().all()
    assert df["trades"].isna().all()


def test_cm_urls_switch_format_on_udiff_start() -> None:
    src = nse_cm.NseCmBhavcopy()
    assert src.urls(dt.date(2024, 7, 5))[0].endswith("EQUITIES/2024/JUL/cm05JUL2024bhav.csv.zip")
    assert src.urls(dt.date(2024, 7, 8))[0].endswith("BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv.zip")


def test_cm_bad_layout_raises_format_changed() -> None:
    with pytest.raises(FormatChanged, match="expected columns"):
        nse_cm.NseCmBhavcopy().parse(b"FOO,BAR\n1,2\n", dt.date(2026, 1, 1))


def test_fo_udiff_and_legacy_share_schema() -> None:
    src = nse_fo.NseFoBhavcopy()
    new = src.parse(fixture_bytes("BhavCopy_NSE_FO_0_0_0_20261019_F_0000.csv.zip"), dt.date(2026, 10, 19))
    old = src.parse(fixture_bytes("fo02JAN2023bhav.csv.zip"), dt.date(2023, 1, 2))
    assert list(new.columns) == list(old.columns) == list(nse_fo.COLUMNS)
    assert set(new["instrument"]) <= {"FUTIDX", "FUTSTK", "OPTIDX", "OPTSTK"}
    fut = new[(new["symbol"] == "NIFTY") & (new["instrument"] == "FUTIDX")]
    assert (fut["option_type"] == "XX").all() and (fut["strike"] == 0).all()
    assert new["lot_size"].dropna().gt(0).all()
    ofut = old[old["instrument"] == "FUTIDX"].iloc[0]
    assert ofut["turnover"] > 1e7, "VAL_INLAKH must be converted to rupees"


def test_index_close_canonical_names() -> None:
    src = nse_indices.NseIndexClose()
    new = src.parse(fixture_bytes("ind_close_all_19102026.csv"), dt.date(2026, 10, 19))
    old = src.parse(fixture_bytes("ind_close_all_02012013.csv"), dt.date(2013, 1, 2))
    assert "NIFTY 50" in set(new["index"]) and "NIFTY 50" in set(old["index"])
    assert "NIFTY BANK" in set(old["index"]) and "NIFTY NEXT 50" in set(old["index"])
    n50 = new[new["index"] == "NIFTY 50"].iloc[0]
    assert n50["close"] == pytest.approx(22888.95)
    assert n50["turnover"] == pytest.approx(29268.11e7)


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("S&P CNX Nifty", "NIFTY 50"),
        ("CNX Nifty", "NIFTY 50"),
        ("Nifty 50", "NIFTY 50"),
        ("nifty", "NIFTY 50"),
        ("CNX Nifty Junior", "NIFTY NEXT 50"),
        ("BANKNIFTY", "NIFTY BANK"),
        ("CNX Bank", "NIFTY BANK"),
        ("CNX Midcap", "NIFTY MIDCAP 100"),
        ("Nifty Free Float Midcap 100", "NIFTY MIDCAP 100"),
        ("S&P CNX 500", "NIFTY 500"),
        ("FINNIFTY", "NIFTY FINANCIAL SERVICES"),
        ("India VIX", "INDIA VIX"),
    ],
)
def test_canonical_index(name: str, key: str) -> None:
    assert nse_indices.canonical_index(name) == key


def test_bse_udiff_and_legacy() -> None:
    src = bse_cm.BseCmBhavcopy()
    new = src.parse(fixture_bytes("BhavCopy_BSE_CM_0_0_0_20261019_F_0000.CSV"), dt.date(2026, 10, 19))
    old = src.parse(fixture_bytes("EQ_ISINCODE_190624.zip"), dt.date(2024, 6, 19))
    assert list(new.columns) == list(old.columns) == list(bse_cm.COLUMNS)
    rel = new[new["scrip_code"] == "500325"].iloc[0]
    assert rel["symbol"] == "RELIANCE" and rel["isin"] == "INE002A01018"
    assert old["symbol"].isna().all() and old["date"].unique().tolist() == ["2024-06-19"]


def test_bse_html_shell_means_not_available() -> None:
    with pytest.raises(NotAvailable):
        bse_cm.BseCmBhavcopy().parse(b"<!DOCTYPE html><html>", dt.date(2026, 10, 20))


def test_symbol_files() -> None:
    eq = nse_symbols.parse_equity_list(fixture_bytes("EQUITY_L.csv"))
    assert {"symbol", "isin", "listing_date", "face_value"} <= set(eq.columns)
    assert eq.set_index("symbol").at["RELIANCE", "isin"] == "INE002A01018"
    assert eq.set_index("symbol").at["20MICRONS", "listing_date"] == "2008-10-06"
    sme = nse_symbols.parse_equity_list(fixture_bytes("SME_EQUITY_L.csv"), "sme")
    assert (sme["board"] == "sme").all() and sme["isin"].str.startswith("IN").all()
    ch = nse_symbols.parse_symbol_changes(fixture_bytes("symbolchange.csv"))
    z = ch[ch["old_symbol"] == "ZOMATO"].iloc[0]
    assert z["new_symbol"] == "ETERNAL" and z["effective_date"] == "2025-04-09"
    nc = nse_symbols.parse_name_changes(fixture_bytes("namechange.csv"))
    assert {"symbol", "old_name", "new_name", "effective_date"} <= set(nc.columns)
    dl = nse_symbols.parse_delisted(fixture_bytes("delisted.csv"))
    assert dl.set_index("symbol").at["HEXAWARE", "delisted_date"] == "2020-11-09"


def test_niftyindices_constituents() -> None:
    df = niftyindices.parse(fixture_bytes("ind_nifty50list.csv"))
    assert len(df) == 50
    assert df["isin"].str.match(r"^IN[A-Z0-9]{10}$").all()


def test_holidays_json() -> None:
    df = nse_holidays.parse(fixture_bytes("holiday-master-2026.json"))
    assert "2026-01-26" in set(df["date"])
    assert (df["segment"] == "CM").all()


def test_lot_sizes() -> None:
    df = nse_lots.parse(fixture_bytes("fo_mktlots.csv"))
    nifty = df[(df["symbol"] == "NIFTY")]
    assert nifty["lot_size"].iloc[0] == 65 and nifty["kind"].iloc[0] == "index"
    assert (df["kind"] == "stock").any()
    assert df["month"].str.match(r"^\d{4}-\d{2}$").all()


def test_option_chain() -> None:
    exp = nse_options.parse_expiries(fixture_bytes("option-chain-contract-info-NIFTY.json"))
    assert exp[0] == "2026-10-27"
    df, meta = nse_options.parse_chain(fixture_bytes("option-chain-v3-NIFTY.json"))
    assert set(df["option_type"]) == {"CE", "PE"}
    assert set(df["strike"]) == {22500.0, 22800.0, 23000.0, 23200.0}
    assert meta["underlying_price"] == pytest.approx(22811.35)
    assert pd.api.types.is_float_dtype(df["iv"])


def test_option_chain_rejects_html() -> None:
    with pytest.raises(FormatChanged):
        nse_options.parse_chain(b"<html>blocked</html>")


def test_deals() -> None:
    hist = nse_deals.parse_history(fixture_bytes("bulk_deals.json"), "bulk")
    assert list(hist.columns) == list(nse_deals.COLUMNS)
    assert hist["date"].str.match(r"^\d{4}-\d{2}-\d{2}$").all()
    today = nse_deals.parse_archive(fixture_bytes("bulk.csv"), "bulk")
    assert today["quantity"].gt(0).all()
    empty = nse_deals.parse_archive(fixture_bytes("block.csv"), "block")
    assert empty.empty


def test_fii_dii() -> None:
    df = nse_fiidii.parse(fixture_bytes("fiidiiTradeReact.json"))
    assert set(df["category"]) == {"FII", "DII"}
    fii = df[df["category"] == "FII"].iloc[0]
    assert fii["net"] == pytest.approx(fii["buy"] - fii["sell"], abs=0.02)

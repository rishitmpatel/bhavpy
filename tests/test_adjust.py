"""Adjustment validation on real NSE prices around real corporate actions.

Each case uses actual bhavcopy closes (tests/fixtures/prices_adjustment_cases.csv) and
NSE's own corporate-action records. The raw series jumps on the ex-date; the adjusted
series must not.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from bhavpy import adjust
from bhavpy.dates import ist_index
from bhavpy.sources.nse_corpactions import parse as parse_ca

from .conftest import FIXTURES, fixture_bytes


def prices(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURES / "prices_adjustment_cases.csv")
    df = df[(df["symbol"] == symbol) & df["date"].between(start, end)].copy()
    df.index = ist_index(pd.to_datetime(df.pop("date")))
    return df


def actions(symbol: str) -> pd.DataFrame:
    return parse_ca(fixture_bytes(f"corporate-actions-{symbol}.json"))


def max_abs_return(s: pd.Series) -> float:
    return float(np.abs(np.log(s / s.shift(1))).dropna().max())


@pytest.mark.parametrize(
    ("symbol", "start", "end", "ex_date", "factor"),
    [
        (
            "RELIANCE",
            "2017-08-28",
            "2017-09-15",
            "2017-09-07",
            0.5,
        ),  # bonus 1:1, legacy file format
        ("RELIANCE", "2024-10-21", "2024-11-04", "2024-10-28", 0.5),  # bonus 1:1, UDiFF format
        ("SHRIRAMFIN", "2025-01-03", "2025-01-16", "2025-01-10", 0.2),  # split FV 10 -> 2
    ],
)
def test_split_and_bonus_make_series_continuous(
    symbol: str, start: str, end: str, ex_date: str, factor: float
) -> None:
    px = prices(symbol, start, end)
    assert max_abs_return(px["close"]) > 0.5, "raw series should show the ex-date jump"
    events = adjust.build_events(actions(symbol), px, mode="split")
    events = events[(events["ex_date"] > px.index[0]) & (events["ex_date"] <= px.index[-1])]
    out = adjust.apply(px, events)
    assert max_abs_return(out["adj_close"]) < 0.08, "adjusted series must be continuous"
    ev = events[events["applied"]]
    assert len(ev) == 1 and ev["ex_date"].iloc[0].strftime("%Y-%m-%d") == ex_date
    assert ev["price_factor"].iloc[0] == pytest.approx(factor)
    assert ev["check"].iloc[0] == "ok"
    before = out.index < pd.Timestamp(ex_date, tz="Asia/Kolkata")
    assert np.allclose(out.loc[before, "adj_close"], out.loc[before, "close"] * factor)
    assert np.allclose(out.loc[~before, "adj_close"], out.loc[~before, "close"])
    assert np.allclose(out.loc[before, "adj_volume"], out.loc[before, "volume"] / factor)
    # adjusted prev_close on the ex-date equals the adjusted previous close
    exd = out.index[~before][0]
    prev = out.index[before][-1]
    assert out.at[exd, "adj_prev_close"] == pytest.approx(out.at[prev, "adj_close"])


def test_rights_issue_uses_theoretical_ex_rights_price() -> None:
    px = prices("RELIANCE", "2020-05-08", "2020-05-20")
    events = adjust.build_events(actions("RELIANCE"), px, mode="split")
    r = events[(events["kind"] == "rights") & events["applied"]]
    assert len(r) == 1
    p = 1479.25  # close on 2020-05-12, the cum-rights day
    s = 1247 + 10  # premium + face value
    expected = (15 * p + 1 * s) / 16 / p
    assert r["price_factor"].iloc[0] == pytest.approx(expected)


def test_total_return_mode_adds_dividends() -> None:
    px = prices("RELIANCE", "2026-05-28", "2026-06-10")
    split_only = adjust.build_events(actions("RELIANCE"), px, mode="split")
    total = adjust.build_events(actions("RELIANCE"), px, mode="total")
    in_range = lambda e: e[(e["ex_date"] > px.index[0]) & (e["ex_date"] <= px.index[-1])]  # noqa: E731
    assert in_range(split_only).empty
    div = in_range(total)
    assert list(div["kind"]) == ["dividend"] and div["amount"].iloc[0] == 6.0
    cum = px.loc[px.index < div["ex_date"].iloc[0], "close"].iloc[-1]
    assert div["price_factor"].iloc[0] == pytest.approx((cum - 6.0) / cum)


def test_cumulative_multiplies_later_events() -> None:
    idx = ist_index(pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"]))
    ev = pd.DataFrame(
        {
            "ex_date": ist_index(pd.to_datetime(["2020-01-02", "2020-01-04"])),
            "price_factor": [0.5, 0.2],
            "applied": [True, True],
        }
    )
    cum = adjust.cumulative(idx, ev)
    assert cum.tolist() == pytest.approx([0.1, 0.2, 0.2, 1.0])


def test_record_contradicted_by_prices_is_flagged_not_applied() -> None:
    px = prices("RELIANCE", "2024-10-21", "2024-11-04")
    fake = pd.DataFrame(
        [{"symbol": "RELIANCE", "series": "EQ", "isin": None, "company": "", "ex_date": "2024-10-23",
          "record_date": None, "face_value": 10.0, "subject": "Bonus 1:1"}]
    )  # fmt: skip
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        events = adjust.build_events(fake, px, mode="split")
    assert any("contradicted by prices" in str(x.message) for x in w)
    row = events[events["kind"] == "bonus"].iloc[0]
    assert row["check"] == "mismatch" and not row["applied"]


def test_unexplained_gap_is_reported_and_optionally_applied() -> None:
    px = prices("SHRIRAMFIN", "2025-01-03", "2025-01-16")
    no_records = pd.DataFrame(
        columns=[
            "symbol",
            "series",
            "isin",
            "company",
            "ex_date",
            "record_date",
            "face_value",
            "subject",
        ]
    )
    ev = adjust.build_events(no_records, px, mode="split")
    gap = ev[ev["kind"] == "unexplained_gap"]
    assert len(gap) == 1 and not gap["applied"].iloc[0]
    assert gap["price_factor"].iloc[0] == pytest.approx(0.2)
    ev2 = adjust.build_events(no_records, px, mode="split", infer=True)
    assert ev2["applied"].any()
    out = adjust.apply(px, ev2)
    assert max_abs_return(out["adj_close"]) < 0.08


def test_feed_failure_turns_on_inference() -> None:
    px = prices("SHRIRAMFIN", "2025-01-03", "2025-01-16")
    empty = pd.DataFrame(
        columns=[
            "symbol",
            "series",
            "isin",
            "company",
            "ex_date",
            "record_date",
            "face_value",
            "subject",
        ]
    )
    empty.attrs["feed_ok"] = False
    ev = adjust.build_events(empty, px)
    assert ev["applied"].any()


def test_reused_ticker_records_stay_in_their_window(
    tmp_cache: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime as dt

    from bhavpy import cache, symbols
    from bhavpy.sources import nse_corpactions as ca_src

    switch = dt.date(2020, 1, 1)
    chain = [symbols.Segment("OLDCO", None, switch), symbols.Segment("NEWCO", switch, None)]
    monkeypatch.setattr(symbols, "symbol_chain", lambda s: chain)
    cache.ensure_table("corp_actions", adjust._CA_DDL)
    rows = pd.DataFrame(
        [
            ["OLDCO", "EQ", None, "Old Co", "2018-05-01", None, 10.0, "Bonus 1:1"],
            ["OLDCO", "EQ", None, "Another Co", "2023-05-01", None, 10.0, "Bonus 1:1"],  # ticker reused
            ["NEWCO", "EQ", None, "Old Co", "2021-05-01", None, 10.0, "Bonus 1:2"],
        ],
        columns=list(ca_src.COLUMNS),
    )
    cache.write_frame("corp_actions", rows, ca_src.COLUMNS)
    for s in ("OLDCO", "NEWCO"):
        cache.blob_put(f"corp_actions_fetched:{s}", b"1")
    got = adjust.corporate_actions("NEWCO")
    assert got["ex_date"].tolist() == ["2018-05-01", "2021-05-01"]


def test_split_and_bonus_on_same_ex_date_are_checked_together() -> None:
    # BAJFINANCE 2025-06-16: bonus 4:1 and split FV 2 -> 1 on one day (combined factor 0.1).
    px = prices("BAJFINANCE", "2025-06-09", "2025-06-20")
    events = adjust.build_events(actions("BAJFINANCE"), px)
    day = events[events["ex_date"] == pd.Timestamp("2025-06-16", tz="Asia/Kolkata")]
    assert set(day["kind"]) == {"bonus", "split"}
    assert day["applied"].all() and (day["check"] == "ok").all()
    assert day["price_factor"].prod() == pytest.approx(0.1)
    out = adjust.apply(px, events[(events["ex_date"] > px.index[0]) & (events["ex_date"] <= px.index[-1])])
    assert max_abs_return(out["adj_close"]) < 0.08


def test_demerger_is_estimated_from_price_discovery() -> None:
    # RELIANCE 2023-07-20, Jio Financial Services demerger: special pre-open discovered 2,580.
    px = prices("RELIANCE", "2023-07-14", "2023-07-26")
    events = adjust.build_events(actions("RELIANCE"), px)
    dm = events[events["kind"] == "demerger"].iloc[0]
    assert dm["check"] == "estimated" and dm["applied"]
    assert dm["price_factor"] == pytest.approx(2580.0 / 2841.85)
    ignored = adjust.build_events(actions("RELIANCE"), px, demerger="ignore")
    assert ignored.loc[ignored["kind"] == "demerger", "check"].iloc[0] == "not_adjusted"

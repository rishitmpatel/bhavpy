from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from bhavpy import indices
from bhavpy.sources import niftyindices
from bhavpy.sources.nse_symbols import parse_symbol_changes
from bhavpy.symbols import Segment, chain_from

from .conftest import fixture_bytes


@pytest.fixture
def changes() -> pd.DataFrame:
    return parse_symbol_changes(fixture_bytes("symbolchange.csv"))


def test_old_symbol_resolves_forward(changes: pd.DataFrame) -> None:
    chain = chain_from("ZOMATO", changes, listed={"ETERNAL", "RELIANCE"})
    assert chain == [
        Segment("ZOMATO", None, dt.date(2025, 4, 9)),
        Segment("ETERNAL", dt.date(2025, 4, 9), None),
    ]


def test_multi_hop_chain(changes: pd.DataFrame) -> None:
    chain = chain_from("TELCO", changes, listed={"TMPV"})
    assert [s.symbol for s in chain] == ["TELCO", "TATAMOTORS", "TMPV"]
    assert chain[1].start == dt.date(2003, 12, 26) and chain[1].end == dt.date(2025, 10, 24)
    vedl = chain_from("SESAGOA", changes, listed={"VEDL"})
    assert [s.symbol for s in vedl] == ["SESAGOA", "SSLT", "VEDL"]


def test_current_symbol_gets_its_past(changes: pd.DataFrame) -> None:
    chain = chain_from("ETERNAL", changes, listed={"ETERNAL"})
    assert [s.symbol for s in chain] == ["ZOMATO", "ETERNAL"]


def test_unknown_symbol_is_single_segment(changes: pd.DataFrame) -> None:
    assert chain_from("tcs.ns", changes, listed={"TCS"}) == [Segment("TCS", None, None)]


def test_nifty50_walk_keeps_fifty_members_at_every_change() -> None:
    current = set(niftyindices.parse(fixture_bytes("ind_nifty50list.csv"))["symbol"])
    assert len(current) == 50
    log = indices.nifty50_changes()
    members = set(current)
    for eff, grp in log.sort_values("effective_date", ascending=False).groupby("effective_date", sort=False):
        for row in grp.itertuples():
            assert row.added in members, f"{eff}: {row.added} should be a member after the change"
            assert row.removed not in members, f"{eff}: {row.removed} should not be a member after the change"
        for row in grp.itertuples():
            members.discard(row.added)
            members.add(row.removed)
        assert len(members) == 50, eff
    # spot checks from NSE press releases
    assert "HDFC" in indices.nifty50_members(dt.date(2023, 7, 12), current)
    assert "HDFC" not in indices.nifty50_members(dt.date(2023, 7, 13), current)
    assert "YESBANK" in indices.nifty50_members(dt.date(2019, 1, 1), current)


def test_constituent_file_codes_cover_major_indices() -> None:
    for name in ("NIFTY 50", "NIFTY 500", "NIFTY BANK", "NIFTY IT", "NIFTY MIDCAP 150"):
        assert niftyindices.url_for(name).endswith("list.csv")

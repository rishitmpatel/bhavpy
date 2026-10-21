"""Corporate-action subject parsing, on real NSE spellings."""

from __future__ import annotations

import pytest

from bhavpy.sources.nse_corpactions import Event, parse, parse_subject

from .conftest import fixture_bytes

CASES = [
    ("Bonus 1:1", [Event("bonus", 1, 1)]),
    (" Bonus 1:2", [Event("bonus", 1, 2)]),
    ("Bonus 4: 1", [Event("bonus", 4, 1)]),
    (
        "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
        [Event("split", 10, 2)],
    ),
    (
        "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share",
        [Event("split", 10, 1)],
    ),
    ("Face Value Split From Rs.10/- To Rs.5/-", [Event("split", 10, 5)]),
    ("Fv Splt Frm Rs 10 To Rs 2", [Event("split", 10, 2)]),
    ("Fv Split Rs.2 To Rs.1", [Event("split", 2, 1)]),
    ("Consolidation Of Shares From Rs 1 To Rs 10", [Event("consolidation", 1, 10)]),
    ("Rights 1:15 @ Premium Rs 1247", [Event("rights", 1, 15, 1257.0)]),
    ("Rights 5:41 @ Premium Rs 109/-", [Event("rights", 5, 41, 119.0)]),
    (
        "Rights Eq 1:20 @ Premium Rs.715 Per Share And 3 Warrants : 1 Eq",
        [Event("rights", 1, 20, 725.0)],
    ),
    ("Rights 3:11", [Event("rights", 3, 11, None)]),
    ("Dividend - Rs 6 Per Share", [Event("dividend", amount=6.0)]),
    ("Dividend - Re 0.50 Per Share", [Event("dividend", amount=0.5)]),
    ("Interim Dividend - Rs 5/- Per Share (Purpose Revised)", [Event("dividend", amount=5.0)]),
    ("Int Div-Rs.2.50/- Per Share Purpose Revised", [Event("dividend", amount=2.5)]),
    ("Agm/Div-Re.0.50 Per Share", [Event("dividend", amount=0.5)]),
    ("Annual General Meeting And Dividend Rs.8/- Per Share", [Event("dividend", amount=8.0)]),
    ("Annual General Meeting/Divdiend Of Rs.3.50 Per Share", [Event("dividend", amount=3.5)]),
    ("Interim Divided - Rs 2.50/- Per Share", [Event("dividend", amount=2.5)]),
    (
        "Annual General Meeting/Dividend - Rs 6 Per Share/Special Dividend - Rs 5 Per Share",
        [Event("dividend", amount=6.0), Event("dividend", amount=5.0)],
    ),
    ("Dividend 50%", [Event("dividend", amount=5.0)]),  # with face value 10
    ("Distribution - Rs 2.10 Per Unit", [Event("dividend", amount=2.1)]),
    ("Demerger", [Event("demerger")]),
    ("Annual General Meeting", []),
    ("Interest Payment", []),
    ("Buy Back", []),
    ("Annual General Meeting/Dividend - Rs  Per Sh/", []),
]


@pytest.mark.parametrize(("subject", "expected"), CASES)
def test_parse_subject(subject: str, expected: list[Event]) -> None:
    assert parse_subject(subject, face_value=10.0) == expected


def test_split_text_is_not_a_dividend() -> None:
    ev = parse_subject("Face Value Split (Sub-Division) - From Rs 5/- Per Share To Rs 2/- Per Share")
    assert [e.kind for e in ev] == ["split"]


def test_percent_dividend_needs_face_value() -> None:
    assert parse_subject("Dividend 50%", face_value=None) == []


def test_parse_json_reliance() -> None:
    df = parse(fixture_bytes("corporate-actions-RELIANCE.json"))
    assert {"ex_date", "subject", "face_value", "isin"} <= set(df.columns)
    bonus = df[df["subject"].str.contains("Bonus")]
    assert {"2009-11-26", "2017-09-07", "2024-10-28"} <= set(bonus["ex_date"])
    assert df["ex_date"].str.match(r"^\d{4}-\d{2}-\d{2}$").all()

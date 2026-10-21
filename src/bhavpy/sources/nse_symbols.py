"""NSE security master files (all plain CSV under nsearchives.nseindia.com).

* ``content/equities/EQUITY_L.csv``          - listed main-board equities, with ISIN
* ``emerge/corporates/content/SME_EQUITY_L.csv`` - listed SME (Emerge) equities
* ``content/equities/symbolchange.csv``      - every symbol change with effective date
* ``content/equities/namechange.csv``        - company name changes
* ``content/equities/delisted.csv``          - delisted companies
"""

from __future__ import annotations

import pandas as pd

from .base import dates, read_csv, require

BASE = "https://nsearchives.nseindia.com/"
URLS = {
    "equity_list": BASE + "content/equities/EQUITY_L.csv",
    "sme_list": BASE + "emerge/corporates/content/SME_EQUITY_L.csv",
    "symbol_changes": BASE + "content/equities/symbolchange.csv",
    "name_changes": BASE + "content/equities/namechange.csv",
    "delisted": BASE + "content/equities/delisted.csv",
}


def _col(df: pd.DataFrame, *names: str) -> pd.Series:
    for n in names:
        if n in df.columns:
            return df[n]
    raise KeyError(names)


def parse_equity_list(raw: bytes, board: str = "main") -> pd.DataFrame:
    df = read_csv(raw)
    df.columns = [c.upper().replace("_", " ") for c in df.columns]
    require(
        df,
        ["SYMBOL", "SERIES", "DATE OF LISTING", "ISIN NUMBER", "FACE VALUE"],
        f"NSE {board} equity list",
    )
    return pd.DataFrame(
        {
            "symbol": df["SYMBOL"],
            "name": _col(df, "NAME OF COMPANY"),
            "series": df["SERIES"],
            "listing_date": dates(df["DATE OF LISTING"]),
            "isin": df["ISIN NUMBER"],
            "face_value": pd.to_numeric(df["FACE VALUE"], errors="coerce"),
            "market_lot": pd.to_numeric(df["MARKET LOT"], errors="coerce") if "MARKET LOT" in df else 1,
            "board": board,
        }
    )


def parse_symbol_changes(raw: bytes) -> pd.DataFrame:
    df = read_csv(raw)
    df.columns = [c.upper() for c in df.columns]
    require(df, ["OLD SYMBOL", "NEW SYMBOL", "EFFECTIVE DATE"], "NSE symbol change file")
    out = pd.DataFrame(
        {
            "old_symbol": df["OLD SYMBOL"],
            "new_symbol": df["NEW SYMBOL"],
            "effective_date": dates(df["EFFECTIVE DATE"], "%d-%b-%Y"),
            "name": _col(df, "NAME OF THE COMPANY", "COMPANY NAME"),
        }
    )
    out = out[(out["old_symbol"] != "") & (out["new_symbol"] != "")]
    return out.dropna(subset=["effective_date"]).reset_index(drop=True)


def parse_name_changes(raw: bytes) -> pd.DataFrame:
    df = read_csv(raw)
    df.columns = [c.upper() for c in df.columns]
    require(
        df,
        ["SYMBOL", "OLD NAME OF THE COMPANY", "NEW NAME OF THE COMPANY", "EFFECTIVE DATE"],
        "NSE name change file",
    )
    return pd.DataFrame(
        {
            "symbol": df["SYMBOL"],
            "old_name": df["OLD NAME OF THE COMPANY"],
            "new_name": df["NEW NAME OF THE COMPANY"],
            "effective_date": dates(df["EFFECTIVE DATE"], "%d-%b-%Y"),
        }
    ).reset_index(drop=True)


def parse_delisted(raw: bytes) -> pd.DataFrame:
    df = read_csv(raw)
    require(df, ["Symbol", "Company", "Delisted Date"], "NSE delisted file")
    return (
        pd.DataFrame(
            {
                "symbol": df["Symbol"],
                "name": df["Company"],
                "delisted_date": dates(df["Delisted Date"], "%d-%b-%y"),
                "reason": df.get("Type of Delisting", None),
            }
        )
        .query("symbol != ''")
        .reset_index(drop=True)
    )

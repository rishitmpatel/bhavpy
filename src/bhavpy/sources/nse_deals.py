"""Bulk and block deals.

* Today's file: ``https://nsearchives.nseindia.com/content/equities/bulk.csv`` / ``block.csv``
* History (JSON): ``https://www.nseindia.com/api/historicalOR/bulk-block-short-deals?optionType=bulk_deals|block_deals&from=DD-MM-YYYY&to=DD-MM-YYYY``
"""

from __future__ import annotations

import json

import pandas as pd

from ..errors import FormatChanged
from .base import dates, num, read_csv, require

ARCHIVE_URL = {
    "bulk": "https://nsearchives.nseindia.com/content/equities/bulk.csv",
    "block": "https://nsearchives.nseindia.com/content/equities/block.csv",
}
HISTORY_URL = "https://www.nseindia.com/api/historicalOR/bulk-block-short-deals"
COLUMNS = (
    "date",
    "kind",
    "symbol",
    "security_name",
    "client",
    "side",
    "quantity",
    "price",
    "remarks",
)


def history_params(kind: str, start: str, end: str) -> dict[str, str]:
    return {"optionType": f"{kind}_deals", "from": start, "to": end}


def parse_history(raw: bytes, kind: str) -> pd.DataFrame:
    try:
        rows = json.loads(raw)["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise FormatChanged("deals JSON lacks 'data'") from exc
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=list(COLUMNS))
    require(
        df,
        ["BD_DT_DATE", "BD_SYMBOL", "BD_CLIENT_NAME", "BD_BUY_SELL", "BD_QTY_TRD", "BD_TP_WATP"],
        "deals JSON",
    )
    return pd.DataFrame(
        {
            "date": dates(df["BD_DT_DATE"].astype(str), "%d-%b-%Y"),
            "kind": kind,
            "symbol": df["BD_SYMBOL"].astype(str).str.strip(),
            "security_name": df.get("BD_SCRIP_NAME", pd.Series([None] * len(df))),
            "client": df["BD_CLIENT_NAME"].astype(str).str.strip(),
            "side": df["BD_BUY_SELL"].astype(str).str.upper().str.strip(),
            "quantity": pd.to_numeric(df["BD_QTY_TRD"], errors="coerce"),
            "price": pd.to_numeric(df["BD_TP_WATP"], errors="coerce"),
            "remarks": df.get("BD_REMARKS", pd.Series([None] * len(df))),
        }
    )


def parse_archive(raw: bytes, kind: str) -> pd.DataFrame:
    df = read_csv(raw)
    require(df, ["Date", "Symbol", "Client Name", "Buy/Sell", "Quantity Traded"], f"{kind}.csv")
    df = df[df["Date"].str.upper() != "NO RECORDS"]
    price_col = next((c for c in df.columns if c.lower().startswith("trade price")), None)
    return pd.DataFrame(
        {
            "date": dates(df["Date"], "%d-%b-%Y"),
            "kind": kind,
            "symbol": df["Symbol"],
            "security_name": df.get("Security Name"),
            "client": df["Client Name"],
            "side": df["Buy/Sell"].str.upper(),
            "quantity": num(df["Quantity Traded"]),
            "price": num(df[price_col]) if price_col else None,
            "remarks": df.get("Remarks"),
        }
    ).reset_index(drop=True)

"""FII/FPI and DII provisional cash-market activity (latest day only).

``https://www.nseindia.com/api/fiidiiTradeReact`` -> ``[{category, date, buyValue, sellValue, netValue}]``
(values in rupees crore). NSE publishes only the latest day here, so bhavpy stores each
day it sees; run ``bhavpy update`` daily (or on a schedule) to build history.
"""

from __future__ import annotations

import json

import pandas as pd

from ..errors import FormatChanged
from .base import dates

URL = "https://www.nseindia.com/api/fiidiiTradeReact"
COLUMNS = ("date", "category", "buy", "sell", "net")


def parse(raw: bytes) -> pd.DataFrame:
    try:
        rows = json.loads(raw)
        df = pd.DataFrame(rows)
        df = df[["date", "category", "buyValue", "sellValue", "netValue"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise FormatChanged("fiidiiTradeReact JSON changed shape") from exc
    cat = df["category"].astype(str).str.upper().str.replace(" ", "", regex=False)
    return pd.DataFrame(
        {
            "date": dates(df["date"].astype(str), "%d-%b-%Y"),
            "category": cat.map(lambda c: "FII" if c.startswith("FII") or c.startswith("FPI") else c),
            "buy": pd.to_numeric(df["buyValue"], errors="coerce"),
            "sell": pd.to_numeric(df["sellValue"], errors="coerce"),
            "net": pd.to_numeric(df["netValue"], errors="coerce"),
        }
    )

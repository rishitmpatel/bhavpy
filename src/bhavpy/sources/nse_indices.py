"""NSE daily index closing file (all NSE indices, one file per day).

``https://nsearchives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv``
(available from about 2012-03; older index history is not in this archive).

Index names changed over the years (``S&P CNX Nifty`` -> ``CNX Nifty`` -> ``Nifty 50``);
:func:`canonical_index` maps every spelling to one upper-case key.
"""

from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from .base import DailySource, dates, num, read_csv, require

COLUMNS = (
    "date", "index", "open", "high", "low", "close", "volume", "turnover", "pe", "pb",
    "div_yield",
)  # fmt: skip

#: Old official names and common trader shorthands -> current canonical name.
ALIASES = {
    "NIFTY": "NIFTY 50",
    "NIFTY50": "NIFTY 50",
    "NIFTY NIFTY": "NIFTY 50",
    "NIFTY NIFTY JUNIOR": "NIFTY NEXT 50",
    "NIFTY JUNIOR": "NIFTY NEXT 50",
    "NIFTYNXT50": "NIFTY NEXT 50",
    "NIFTYNEXT50": "NIFTY NEXT 50",
    "BANKNIFTY": "NIFTY BANK",
    "NIFTYBANK": "NIFTY BANK",
    "FINNIFTY": "NIFTY FINANCIAL SERVICES",
    "NIFTY FINANCE": "NIFTY FINANCIAL SERVICES",
    "MIDCPNIFTY": "NIFTY MIDCAP SELECT",
    "VIX": "INDIA VIX",
    "NIFTY MIDCAP": "NIFTY MIDCAP 100",
    "NIFTY FREE FLOAT MIDCAP 100": "NIFTY MIDCAP 100",
    "NIFTY SMALLCAP": "NIFTY SMALLCAP 100",
    "NIFTY FREE FLOAT SMALLCAP 100": "NIFTY SMALLCAP 100",
    "NIFTY CONSUMPTION": "NIFTY INDIA CONSUMPTION",
    "NIFTY DIVIDEND OPPORTUNITIES": "NIFTY DIVIDEND OPPORTUNITIES 50",
    "NIFTY SERVICE SECTOR": "NIFTY SERVICES SECTOR",
    "NIFTY NIFTY DIVIDEND": "NIFTY50 DIVIDEND POINTS",
    "NIFTY NIFTY SHARIAH": "NIFTY50 SHARIAH",
    "NIFTY 500 SHARIAH": "NIFTY500 SHARIAH",
    "NIFTY HEALTHCARE INDEX": "NIFTY HEALTHCARE",
    "NIFTY LOW VOLATILITY": "NIFTY LOW VOLATILITY 50",
    "NIFTY ALPHA INDEX": "NIFTY ALPHA 50",
    "NIFTY HIGH BETA": "NIFTY HIGH BETA 50",
    "NIFTY 100 EQUAL WEIGHT": "NIFTY100 EQUAL WEIGHT",
    "NIFTY CPSE": "NIFTY CPSE",
    "CPSE": "NIFTY CPSE",
    "NIFTY SHARIAH25": "NIFTY SHARIAH 25",
    "NSE QUALITY 30": "NIFTY QUALITY 30",
    "NIFTY TOTAL MARKET INDEX": "NIFTY TOTAL MARKET",
}


def canonical_index(name: str) -> str:
    """``'S&P CNX Nifty'``, ``'CNX Nifty'``, ``'nifty'``, ``'Nifty 50'`` -> ``'NIFTY 50'``."""
    key = re.sub(r"\s+", " ", name.strip().upper())
    key = re.sub(r"^S&P CNX ", "NIFTY ", key)
    key = re.sub(r"^CNX ", "NIFTY ", key)
    key = re.sub(r"^S&P ", "", key)
    return ALIASES.get(key, key)


class NseIndexClose(DailySource):
    dataset = "nse_index"
    table = "nse_index"
    columns = COLUMNS
    first_date = dt.date(2012, 3, 1)
    expect = "csv"
    ddl = """
    CREATE TABLE IF NOT EXISTS nse_index (
        date TEXT NOT NULL, "index" TEXT NOT NULL,
        open REAL, high REAL, low REAL, close REAL, volume REAL, turnover REAL,
        pe REAL, pb REAL, div_yield REAL,
        PRIMARY KEY ("index", date)
    ) WITHOUT ROWID;
    """

    def urls(self, day: dt.date) -> list[str]:
        return [f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{day:%d%m%Y}.csv"]

    def parse(self, raw: bytes, day: dt.date) -> pd.DataFrame:
        df = read_csv(raw)
        require(
            df,
            ["Index Name", "Index Date", "Open Index Value", "High Index Value",
             "Low Index Value", "Closing Index Value"],
            "NSE index close file",
        )  # fmt: skip
        out = pd.DataFrame(
            {
                "date": dates(df["Index Date"], "%d-%m-%Y"),
                "index": df["Index Name"].map(canonical_index),
                "open": num(df["Open Index Value"]),
                "high": num(df["High Index Value"]),
                "low": num(df["Low Index Value"]),
                "close": num(df["Closing Index Value"]),
                "volume": num(df["Volume"]) if "Volume" in df else None,
                "turnover": num(df["Turnover (Rs. Cr.)"], 1e7) if "Turnover (Rs. Cr.)" in df else None,
                "pe": num(df["P/E"]) if "P/E" in df else None,
                "pb": num(df["P/B"]) if "P/B" in df else None,
                "div_yield": num(df["Div Yield"]) if "Div Yield" in df else None,
            }
        )
        out = out.dropna(subset=["date", "close"])
        return out.drop_duplicates(subset=["index", "date"], keep="first").reset_index(drop=True)

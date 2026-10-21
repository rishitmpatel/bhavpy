"""NSE capital-market (equity) daily bhavcopy.

Two layouts exist:

* **UDiFF** (from 2024-07-08):
  ``https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip``
* **Legacy** (1994-11-03 to 2024-07-05):
  ``https://nsearchives.nseindia.com/content/historical/EQUITIES/YYYY/MON/cmDDMONYYYYbhav.csv.zip``

Note: ``prev_close`` in both layouts is the *unadjusted* previous close; it is not
rebased on split/bonus ex-dates (checked on RELIANCE 2017-09-07 and 2024-10-28).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .base import DailySource, dates, num, read_csv, require, unzip_first

UDIFF_START = dt.date(2024, 7, 8)
_MON = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

#: Equity-like series kept by default (ETFs trade as EQ). Bonds, G-secs, SGBs etc. are dropped.
EQUITY_SERIES = frozenset({"EQ", "BE", "BZ", "BT", "SM", "ST", "SZ", "RR", "IV", "E1"})

COLUMNS = (
    "date", "symbol", "series", "isin", "open", "high", "low", "close", "last",
    "prev_close", "volume", "turnover", "trades",
)  # fmt: skip


class NseCmBhavcopy(DailySource):
    dataset = "nse_cm"
    table = "nse_cm"
    columns = COLUMNS
    first_date = dt.date(1994, 11, 3)
    expect = "zip"
    int_date = True
    paise_columns = ("open", "high", "low", "close", "last", "prev_close")
    int_columns = ("volume", "turnover", "trades")
    ddl = """
    CREATE TABLE IF NOT EXISTS nse_cm (
        date INTEGER NOT NULL, symbol TEXT NOT NULL, series TEXT NOT NULL, isin TEXT,
        open INTEGER, high INTEGER, low INTEGER, close INTEGER, last INTEGER, prev_close INTEGER,
        volume INTEGER, turnover INTEGER, trades INTEGER
    );
    CREATE UNIQUE INDEX IF NOT EXISTS nse_cm_key ON nse_cm(symbol, series, date);
    CREATE INDEX IF NOT EXISTS nse_cm_date ON nse_cm(date);
    """

    def __init__(self, series: frozenset[str] | None = EQUITY_SERIES) -> None:
        self.series = series

    def urls(self, day: dt.date) -> list[str]:
        if day >= UDIFF_START:
            return [
                "https://nsearchives.nseindia.com/content/cm/"
                f"BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
            ]
        mon = _MON[day.month - 1]
        return [
            "https://nsearchives.nseindia.com/content/historical/EQUITIES/"
            f"{day.year}/{mon}/cm{day:%d}{mon}{day.year}bhav.csv.zip"
        ]

    def parse(self, raw: bytes, day: dt.date) -> pd.DataFrame:
        body = unzip_first(raw) if raw[:2] == b"PK" else raw
        df = read_csv(body)
        out = parse_udiff(df) if "TckrSymb" in df.columns else parse_legacy(df, day)
        if self.series is not None:
            out = out[out["series"].isin(self.series)]
        return out.reset_index(drop=True)


def parse_udiff(df: pd.DataFrame) -> pd.DataFrame:
    require(
        df,
        ["TradDt", "TckrSymb", "SctySrs", "ISIN", "OpnPric", "HghPric", "LwPric", "ClsPric",
         "LastPric", "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd"],
        "NSE CM UDiFF bhavcopy",
    )  # fmt: skip
    if "FinInstrmTp" in df.columns:
        df = df[df["FinInstrmTp"].isin(["STK", ""])]
    return pd.DataFrame(
        {
            "date": dates(df["TradDt"], "%Y-%m-%d"),
            "symbol": df["TckrSymb"],
            "series": df["SctySrs"],
            "isin": df["ISIN"].replace("", None),
            "open": num(df["OpnPric"]),
            "high": num(df["HghPric"]),
            "low": num(df["LwPric"]),
            "close": num(df["ClsPric"]),
            "last": num(df["LastPric"]),
            "prev_close": num(df["PrvsClsgPric"]),
            "volume": num(df["TtlTradgVol"]),
            "turnover": num(df["TtlTrfVal"]),
            "trades": num(df["TtlNbOfTxsExctd"]),
        }
    )


def parse_legacy(df: pd.DataFrame, day: dt.date) -> pd.DataFrame:
    require(
        df,
        ["SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "LAST", "PREVCLOSE",
         "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP"],
        "NSE CM legacy bhavcopy",
    )  # fmt: skip
    n = len(df)
    return pd.DataFrame(
        {
            "date": dates(df["TIMESTAMP"], "%d-%b-%Y"),
            "symbol": df["SYMBOL"],
            "series": df["SERIES"],
            "isin": df["ISIN"].replace("", None) if "ISIN" in df.columns else [None] * n,
            "open": num(df["OPEN"]),
            "high": num(df["HIGH"]),
            "low": num(df["LOW"]),
            "close": num(df["CLOSE"]),
            "last": num(df["LAST"]),
            "prev_close": num(df["PREVCLOSE"]),
            "volume": num(df["TOTTRDQTY"]),
            "turnover": num(df["TOTTRDVAL"]),
            "trades": num(df["TOTALTRADES"]) if "TOTALTRADES" in df.columns else [None] * n,
        }
    )

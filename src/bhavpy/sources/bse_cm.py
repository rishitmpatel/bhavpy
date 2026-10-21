"""BSE equity daily bhavcopy.

* **UDiFF** (from 2024-07-08):
  ``https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV``
* **Legacy** (2017-01 to 2024-07-05): ``https://www.bseindia.com/download/BhavCopy/Equity/EQ_ISINCODE_DDMMYY.zip``

The legacy file has no ticker symbol (only scrip code + short name), so ``symbol`` is
empty before 2024-07-08; use ``scrip_code`` or ``isin`` to identify securities.
BSE answers missing days with an HTML page and HTTP 200, which is treated as "not available".
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from ..errors import NotAvailable
from .base import DailySource, dates, num, read_csv, require, unzip_first
from .nse_cm import UDIFF_START

COLUMNS = (
    "date", "scrip_code", "symbol", "name", "group", "isin", "open", "high", "low", "close",
    "last", "prev_close", "volume", "turnover", "trades",
)  # fmt: skip


class BseCmBhavcopy(DailySource):
    dataset = "bse_cm"
    table = "bse_cm"
    columns = COLUMNS
    first_date = dt.date(2017, 1, 1)  # older EQ_ISINCODE files are no longer served
    expect = "csv"
    int_date = True
    paise_columns = ("open", "high", "low", "close", "last", "prev_close")
    int_columns = ("volume", "turnover", "trades")
    ddl = """
    CREATE TABLE IF NOT EXISTS bse_cm (
        date INTEGER NOT NULL, scrip_code TEXT NOT NULL, symbol TEXT, name TEXT, "group" TEXT,
        isin TEXT, open INTEGER, high INTEGER, low INTEGER, close INTEGER, last INTEGER,
        prev_close INTEGER, volume INTEGER, turnover INTEGER, trades INTEGER
    );
    CREATE UNIQUE INDEX IF NOT EXISTS bse_cm_key ON bse_cm(scrip_code, date);
    CREATE INDEX IF NOT EXISTS bse_cm_isin ON bse_cm(isin);
    """

    def urls(self, day: dt.date) -> list[str]:
        base = "https://www.bseindia.com/download/BhavCopy/Equity/"
        if day >= UDIFF_START:
            return [f"{base}BhavCopy_BSE_CM_0_0_0_{day:%Y%m%d}_F_0000.CSV"]
        return [f"{base}EQ_ISINCODE_{day:%d%m%y}.zip"]

    def expect_for(self, url: str) -> str:
        # BSE serves its SPA shell (HTML, HTTP 200) for missing files; let parse() decide.
        return "any"

    def parse(self, raw: bytes, day: dt.date) -> pd.DataFrame:
        if raw.lstrip()[:1] == b"<":
            raise NotAvailable(f"BSE has no bhavcopy for {day}")
        body = unzip_first(raw) if raw[:2] == b"PK" else raw
        df = read_csv(body)
        if "TckrSymb" in df.columns:
            return parse_udiff(df)
        return parse_legacy(df)


def parse_udiff(df: pd.DataFrame) -> pd.DataFrame:
    require(
        df,
        ["TradDt", "FinInstrmId", "TckrSymb", "ISIN", "OpnPric", "HghPric", "LwPric",
         "ClsPric", "LastPric", "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal"],
        "BSE UDiFF bhavcopy",
    )  # fmt: skip
    return pd.DataFrame(
        {
            "date": dates(df["TradDt"], "%Y-%m-%d"),
            "scrip_code": df["FinInstrmId"],
            "symbol": df["TckrSymb"],
            "name": df.get("FinInstrmNm", None),
            "group": df.get("SctySrs", None),
            "isin": df["ISIN"].replace("", None),
            "open": num(df["OpnPric"]),
            "high": num(df["HghPric"]),
            "low": num(df["LwPric"]),
            "close": num(df["ClsPric"]),
            "last": num(df["LastPric"]),
            "prev_close": num(df["PrvsClsgPric"]),
            "volume": num(df["TtlTradgVol"]),
            "turnover": num(df["TtlTrfVal"]),
            "trades": num(df["TtlNbOfTxsExctd"]) if "TtlNbOfTxsExctd" in df else None,
        }
    ).reset_index(drop=True)


def parse_legacy(df: pd.DataFrame) -> pd.DataFrame:
    require(
        df,
        ["SC_CODE", "SC_NAME", "OPEN", "HIGH", "LOW", "CLOSE", "LAST", "PREVCLOSE",
         "NO_OF_SHRS", "NET_TURNOV", "ISIN_CODE", "TRADING_DATE"],
        "BSE legacy bhavcopy",
    )  # fmt: skip
    return pd.DataFrame(
        {
            "date": dates(df["TRADING_DATE"], "%d-%b-%y"),
            "scrip_code": df["SC_CODE"],
            "symbol": None,
            "name": df["SC_NAME"],
            "group": df.get("SC_GROUP", None),
            "isin": df["ISIN_CODE"].replace("", None),
            "open": num(df["OPEN"]),
            "high": num(df["HIGH"]),
            "low": num(df["LOW"]),
            "close": num(df["CLOSE"]),
            "last": num(df["LAST"]),
            "prev_close": num(df["PREVCLOSE"]),
            "volume": num(df["NO_OF_SHRS"]),
            "turnover": num(df["NET_TURNOV"]),
            "trades": num(df["NO_TRADES"]) if "NO_TRADES" in df else None,
        }
    ).reset_index(drop=True)

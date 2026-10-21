"""NSE equity-derivatives (F&O) daily bhavcopy.

* **UDiFF** (from 2024-07-08):
  ``https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip``
* **Legacy** (2000-06-12 to 2024-07-05):
  ``https://nsearchives.nseindia.com/content/historical/DERIVATIVES/YYYY/MON/foDDMONYYYYbhav.csv.zip``

Canonical units: ``contracts`` = number of contracts, ``turnover`` = rupees (notional,
as published), ``oi`` = open interest in shares/units.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .base import DailySource, dates, num, read_csv, require, unzip_first
from .nse_cm import _MON, UDIFF_START

COLUMNS = (
    "date", "instrument", "symbol", "expiry", "strike", "option_type", "open", "high",
    "low", "close", "settle", "contracts", "turnover", "oi", "chg_oi", "underlying_price",
    "lot_size",
)  # fmt: skip

_UDIFF_INSTRUMENT = {"IDF": "FUTIDX", "STF": "FUTSTK", "IDO": "OPTIDX", "STO": "OPTSTK"}


class NseFoBhavcopy(DailySource):
    dataset = "nse_fo"
    table = "nse_fut"
    columns = COLUMNS
    first_date = dt.date(2000, 6, 12)
    expect = "zip"
    int_date = True
    ddl = """
    CREATE TABLE IF NOT EXISTS nse_fut (
        date INTEGER NOT NULL, instrument TEXT NOT NULL, symbol TEXT NOT NULL, expiry TEXT NOT NULL,
        strike REAL NOT NULL, option_type TEXT NOT NULL,
        open REAL, high REAL, low REAL, close REAL, settle REAL, contracts REAL, turnover REAL,
        oi REAL, chg_oi REAL, underlying_price REAL, lot_size REAL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS nse_fut_key ON nse_fut(symbol, date, instrument, expiry);
    """

    def for_storage(self, df: pd.DataFrame) -> pd.DataFrame:
        # Only futures go into the table (~1-2% of rows); full files incl. options are
        # cached as raw blobs on demand by bhavpy.fno.bhavcopy().
        return super().for_storage(df[df["instrument"].str.startswith("FUT")])

    def urls(self, day: dt.date) -> list[str]:
        if day >= UDIFF_START:
            return [
                "https://nsearchives.nseindia.com/content/fo/"
                f"BhavCopy_NSE_FO_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
            ]
        mon = _MON[day.month - 1]
        return [
            "https://nsearchives.nseindia.com/content/historical/DERIVATIVES/"
            f"{day.year}/{mon}/fo{day:%d}{mon}{day.year}bhav.csv.zip"
        ]

    def parse(self, raw: bytes, day: dt.date) -> pd.DataFrame:
        body = unzip_first(raw) if raw[:2] == b"PK" else raw
        df = read_csv(body)
        out = parse_udiff(df) if "TckrSymb" in df.columns else parse_legacy(df)
        return out.reset_index(drop=True)


def parse_udiff(df: pd.DataFrame) -> pd.DataFrame:
    require(
        df,
        ["TradDt", "FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric", "OptnTp", "OpnPric",
         "HghPric", "LwPric", "ClsPric", "SttlmPric", "OpnIntrst", "ChngInOpnIntrst",
         "TtlTradgVol", "TtlTrfVal"],
        "NSE F&O UDiFF bhavcopy",
    )  # fmt: skip
    opt = df["OptnTp"].replace("", "XX")
    return pd.DataFrame(
        {
            "date": dates(df["TradDt"], "%Y-%m-%d"),
            "instrument": df["FinInstrmTp"].map(_UDIFF_INSTRUMENT).fillna(df["FinInstrmTp"]),
            "symbol": df["TckrSymb"],
            "expiry": dates(df["XpryDt"], "%Y-%m-%d"),
            "strike": num(df["StrkPric"]).fillna(0.0),
            "option_type": opt,
            "open": num(df["OpnPric"]),
            "high": num(df["HghPric"]),
            "low": num(df["LwPric"]),
            "close": num(df["ClsPric"]),
            "settle": num(df["SttlmPric"]),
            "contracts": num(df["TtlTradgVol"]),
            "turnover": num(df["TtlTrfVal"]),
            "oi": num(df["OpnIntrst"]),
            "chg_oi": num(df["ChngInOpnIntrst"]),
            "underlying_price": num(df["UndrlygPric"]) if "UndrlygPric" in df else None,
            "lot_size": num(df["NewBrdLotQty"]) if "NewBrdLotQty" in df else None,
        }
    )


def parse_legacy(df: pd.DataFrame) -> pd.DataFrame:
    require(
        df,
        ["INSTRUMENT", "SYMBOL", "EXPIRY_DT", "STRIKE_PR", "OPTION_TYP", "OPEN", "HIGH",
         "LOW", "CLOSE", "SETTLE_PR", "CONTRACTS", "VAL_INLAKH", "OPEN_INT", "CHG_IN_OI",
         "TIMESTAMP"],
        "NSE F&O legacy bhavcopy",
    )  # fmt: skip
    return pd.DataFrame(
        {
            "date": dates(df["TIMESTAMP"], "%d-%b-%Y"),
            "instrument": df["INSTRUMENT"],
            "symbol": df["SYMBOL"],
            "expiry": dates(df["EXPIRY_DT"], "%d-%b-%Y"),
            "strike": num(df["STRIKE_PR"]).fillna(0.0),
            "option_type": df["OPTION_TYP"].replace("", "XX"),
            "open": num(df["OPEN"]),
            "high": num(df["HIGH"]),
            "low": num(df["LOW"]),
            "close": num(df["CLOSE"]),
            "settle": num(df["SETTLE_PR"]),
            "contracts": num(df["CONTRACTS"]),
            "turnover": num(df["VAL_INLAKH"], 1e5),
            "oi": num(df["OPEN_INT"]),
            "chg_oi": num(df["CHG_IN_OI"]),
            "underlying_price": None,
            "lot_size": None,
        }
    )

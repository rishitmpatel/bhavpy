"""Current index constituents from NSE Indices (niftyindices.com).

``https://www.niftyindices.com/IndexConstituent/ind_<code>list.csv`` - one CSV per index
with columns ``Company Name, Industry, Symbol, Series, ISIN Code``.
These files are snapshots of *today's* membership only.
"""

from __future__ import annotations

import pandas as pd

from .base import read_csv, require

URL = "https://www.niftyindices.com/IndexConstituent/ind_{code}list.csv"

#: canonical index name -> file code
FILES = {
    "NIFTY 50": "nifty50",
    "NIFTY NEXT 50": "niftynext50",
    "NIFTY 100": "nifty100",
    "NIFTY 200": "nifty200",
    "NIFTY 500": "nifty500",
    "NIFTY TOTAL MARKET": "niftytotalmarket",
    "NIFTY MIDCAP 50": "niftymidcap50",
    "NIFTY MIDCAP 100": "niftymidcap100",
    "NIFTY MIDCAP 150": "niftymidcap150",
    "NIFTY SMALLCAP 100": "niftysmallcap100",
    "NIFTY SMALLCAP 250": "niftysmallcap250",
    "NIFTY MICROCAP 250": "niftymicrocap250",
    "NIFTY BANK": "niftybank",
    "NIFTY IT": "niftyit",
    "NIFTY AUTO": "niftyauto",
    "NIFTY FMCG": "niftyfmcg",
    "NIFTY PHARMA": "niftypharma",
    "NIFTY METAL": "niftymetal",
    "NIFTY REALTY": "niftyrealty",
    "NIFTY ENERGY": "niftyenergy",
    "NIFTY FINANCIAL SERVICES": "niftyfinance",
    "NIFTY MEDIA": "niftymedia",
    "NIFTY PSU BANK": "niftypsubank",
    "NIFTY PRIVATE BANK": "nifty_privatebank",
    "NIFTY HEALTHCARE": "niftyhealthcare",
    "NIFTY CONSUMER DURABLES": "niftyconsumerdurables",
    "NIFTY OIL & GAS": "niftyoilgas",
}


def url_for(index: str) -> str:
    return URL.format(code=FILES[index])


def parse(raw: bytes) -> pd.DataFrame:
    df = read_csv(raw)
    require(df, ["Company Name", "Symbol", "ISIN Code"], "niftyindices constituent file")
    return (
        pd.DataFrame(
            {
                "symbol": df["Symbol"],
                "name": df["Company Name"],
                "industry": df.get("Industry", None),
                "series": df.get("Series", None),
                "isin": df["ISIN Code"],
            }
        )
        .query("symbol != ''")
        .reset_index(drop=True)
    )

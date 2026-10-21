"""F&O market lot sizes: ``https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv``.

A wide file (one column per contract month) with two header rows: one for index
derivatives and one ("Derivatives on Individual Securities") for stocks.
"""

from __future__ import annotations

import csv
import io

import pandas as pd

from ..errors import FormatChanged

URL = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"


def parse(raw: bytes) -> pd.DataFrame:
    text = raw.decode("latin-1")
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text))]
    out: list[dict[str, object]] = []
    months: list[str] = []
    kind = "index"
    for r in rows:
        if not r or not any(r):
            continue
        if r[1].upper() == "SYMBOL":
            months = r[2:]
            if "individual" in r[0].lower():
                kind = "stock"
            continue
        if not months:
            raise FormatChanged("fo_mktlots.csv: data before any header row")
        for month, val in zip(months, r[2:], strict=False):
            if month and val:
                try:
                    lot = int(float(val))
                except ValueError:
                    continue
                out.append(
                    {
                        "symbol": r[1],
                        "underlying": r[0],
                        "kind": kind,
                        "month": month,
                        "lot_size": lot,
                    }
                )
    if not out:
        raise FormatChanged("fo_mktlots.csv parsed to zero rows")
    df = pd.DataFrame(out)
    df["month"] = pd.to_datetime(df["month"], format="%b-%y").dt.strftime("%Y-%m")
    return df

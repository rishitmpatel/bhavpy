"""NSE holiday calendar JSON.

``https://www.nseindia.com/api/holiday-master?type=trading&year=YYYY`` returns holidays
per segment (``CM`` = equities, ``FO`` = derivatives, ...). Works for past years too.
"""

from __future__ import annotations

import json

import pandas as pd

from ..dates import parse_nse_date
from ..errors import FormatChanged

URL = "https://www.nseindia.com/api/holiday-master"


def params(year: int) -> dict[str, str]:
    return {"type": "trading", "year": str(year)}


def parse(raw: bytes, segment: str = "CM") -> pd.DataFrame:
    try:
        data = json.loads(raw)
        rows = data[segment]
    except (ValueError, KeyError, TypeError) as exc:
        raise FormatChanged(f"holiday-master JSON lacks segment {segment!r}") from exc
    out = []
    for r in rows:
        try:
            day = parse_nse_date(r["tradingDate"])
        except (KeyError, ValueError) as exc:
            raise FormatChanged(f"holiday-master row without a usable tradingDate: {r}") from exc
        out.append(
            {
                "date": day.isoformat(),
                "description": (r.get("description") or "").strip(),
                "segment": segment,
                "morning_session": r.get("morning_session"),
                "evening_session": r.get("evening_session"),
            }
        )
    return pd.DataFrame(out, columns=["date", "description", "segment", "morning_session", "evening_session"])

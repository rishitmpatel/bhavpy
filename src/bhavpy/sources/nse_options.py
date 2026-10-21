"""Live NSE option chain (snapshot; the only data here not available from archives).

* ``https://www.nseindia.com/api/option-chain-contract-info?symbol=NIFTY`` -> expiries, strikes
* ``https://www.nseindia.com/api/option-chain-v3?type=Indices|Equity&symbol=X&expiry=DD-Mon-YYYY``
"""

from __future__ import annotations

import json

import pandas as pd

from ..dates import parse_nse_date
from ..errors import FormatChanged

CONTRACT_INFO_URL = "https://www.nseindia.com/api/option-chain-contract-info"
CHAIN_URL = "https://www.nseindia.com/api/option-chain-v3"

INDEX_UNDERLYINGS = frozenset({"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"})

COLUMNS = (
    "expiry", "strike", "option_type", "last", "change", "bid", "bid_qty", "ask", "ask_qty",
    "volume", "oi", "chg_oi", "iv", "underlying_price",
)  # fmt: skip


def chain_params(symbol: str, expiry: str) -> dict[str, str]:
    kind = "Indices" if symbol.upper() in INDEX_UNDERLYINGS else "Equity"
    return {"type": kind, "symbol": symbol.upper(), "expiry": expiry}


def parse_expiries(raw: bytes) -> list[str]:
    """Upcoming expiries as ISO dates."""
    try:
        data = json.loads(raw)
        return [parse_nse_date(x).isoformat() for x in data["expiryDates"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise FormatChanged("option-chain-contract-info JSON lacks 'expiryDates'") from exc


def parse_chain(raw: bytes) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return (long-format chain, meta) where meta has ``timestamp`` and ``underlying_price``."""
    try:
        data = json.loads(raw)
        rec = data["records"]
        rows = rec["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise FormatChanged("option chain JSON lacks records.data") from exc
    out = []
    for r in rows:
        for side in ("CE", "PE"):
            leg = r.get(side)
            if not leg:
                continue
            out.append(
                {
                    "expiry": parse_nse_date(
                        leg.get("expiryDate") or r.get("expiryDates") or r["expiryDate"]
                    ).isoformat(),
                    "strike": float(leg.get("strikePrice", r.get("strikePrice"))),
                    "option_type": side,
                    "last": leg.get("lastPrice"),
                    "change": leg.get("change"),
                    "bid": leg.get("buyPrice1", leg.get("bidprice")),
                    "bid_qty": leg.get("buyQuantity1", leg.get("bidQty")),
                    "ask": leg.get("sellPrice1", leg.get("askPrice")),
                    "ask_qty": leg.get("sellQuantity1", leg.get("askQty")),
                    "volume": leg.get("totalTradedVolume"),
                    "oi": leg.get("openInterest"),
                    "chg_oi": leg.get("changeinOpenInterest"),
                    "iv": leg.get("impliedVolatility"),
                    "underlying_price": leg.get("underlyingValue", rec.get("underlyingValue")),
                }
            )
    df = pd.DataFrame(out, columns=list(COLUMNS))
    for c in COLUMNS[1:]:
        if c != "option_type":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    meta = {"timestamp": rec.get("timestamp"), "underlying_price": rec.get("underlyingValue")}
    return df, meta

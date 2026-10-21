"""NSE corporate actions JSON and the parser for its free-text ``subject`` field.

``https://www.nseindia.com/api/corporates-corporateActions?index=equities&symbol=X&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY``

NSE describes each action in a free-text ``subject`` such as
``"Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"`` or
``"Annual General Meeting/Dividend - Rs 6 Per Share/Special Dividend - Rs 5 Per Share"``.
:func:`parse_subject` turns that text into structured events. The spellings below were
collected from several thousand real subjects (2010-2026); tests cover each of them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import pandas as pd

from ..dates import parse_nse_date
from ..errors import FormatChanged

URL = "https://www.nseindia.com/api/corporates-corporateActions"

COLUMNS = ("symbol", "series", "isin", "company", "ex_date", "record_date", "face_value", "subject")


def params(symbol: str | None, start: str, end: str) -> dict[str, str]:
    """``start``/``end`` as DD-MM-YYYY."""
    p = {"index": "equities", "from_date": start, "to_date": end}
    if symbol:
        p["symbol"] = symbol
    return p


def parse(raw: bytes) -> pd.DataFrame:
    try:
        rows = json.loads(raw)
    except ValueError as exc:
        raise FormatChanged("corporate actions response is not JSON") from exc
    if isinstance(rows, dict):  # some deployments wrap the list
        rows = rows.get("data", [])
    if not isinstance(rows, list):
        raise FormatChanged(f"corporate actions JSON has unexpected type {type(rows).__name__}")
    out = []
    for r in rows:
        try:
            ex = parse_nse_date(r["exDate"]).isoformat()
        except (KeyError, ValueError, AttributeError):
            continue  # entries without an ex-date (e.g. some AGMs) carry no price effect
        try:
            rec = parse_nse_date(r.get("recDate") or "").isoformat()
        except ValueError:
            rec = None
        out.append(
            {
                "symbol": (r.get("symbol") or "").strip(),
                "series": (r.get("series") or "").strip(),
                "isin": (r.get("isin") or "").strip() or None,
                "company": (r.get("comp") or "").strip(),
                "ex_date": ex,
                "record_date": rec,
                "face_value": _to_float(r.get("faceVal")),
                "subject": " ".join(str(r.get("subject") or "").split()),
            }
        )
    return pd.DataFrame(out, columns=list(COLUMNS))


def _to_float(x: object) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ subject parsing


@dataclass(frozen=True)
class Event:
    """One price-relevant action parsed from a subject.

    ``kind``: ``split`` | ``consolidation`` | ``bonus`` | ``rights`` | ``dividend`` |
    ``demerger`` | ``scheme_of_arrangement`` | ``capital_reduction``.
    ``a``/``b``: ratio terms (bonus/rights: *a* new for every *b* held; split: FV *a* -> *b*).
    ``amount``: rupees per share (dividend) or issue price (rights).
    """

    kind: str
    a: float | None = None
    b: float | None = None
    amount: float | None = None


_NUM = r"(\d+(?:\.\d+)?)"
_RS = r"(?:rs|re|inr|₹)?\s*\.?\s*"
_DIV = re.compile(
    r"(?:div\w*?|distribution)[^0-9%]*?" + _RS + _NUM + r"\s*(%)?",
    re.I,
)
_BONUS = re.compile(
    r"bonus[\s-]*(?:issue|shares?\s+in\s+the\s+ratio\s+of)?[\s-]*" + _NUM + r"\s*:\s*" + _NUM, re.I
)
_SPLIT = re.compile(
    r"(?:split|splt|sub-?\s*division)[^0-9]*?" + _RS + _NUM + r"[^0-9]*?\bto\b\s*" + _RS + _NUM,
    re.I,
)
_CONSOL = re.compile(r"consolidat\w*[^0-9]*?" + _RS + _NUM + r"[^0-9]*?\bto\b\s*" + _RS + _NUM, re.I)
_RIGHTS = re.compile(r"(?:rights?|rght)[-\s]*(?:issue|eq)?[-\s]*" + _NUM + r"\s*:\s*" + _NUM, re.I)
_PREMIUM = re.compile(r"premium\s*(?:of\s*)?" + _RS + _NUM, re.I)
_AT_PRICE = re.compile(r"@\s*(?:rs|re|inr|₹)\s*\.?\s*" + _NUM, re.I)


_SCHEME_WORDS = ("scheme of arrangement", "scheme of arangement", "sch of agmt")


def parse_subject(subject: str, face_value: float | None = None) -> list[Event]:
    """Extract every price-relevant event from one NSE corporate-action subject."""
    s = " ".join(subject.split())
    low = s.lower()
    events: list[Event] = []

    for m in _CONSOL.finditer(s):
        events.append(Event("consolidation", float(m.group(1)), float(m.group(2))))
    if not any(e.kind == "consolidation" for e in events):
        for m in _SPLIT.finditer(s):
            a, b = float(m.group(1)), float(m.group(2))
            if a > 0 and b > 0 and a != b:
                events.append(Event("split" if b < a else "consolidation", a, b))
    for m in _BONUS.finditer(s):
        events.append(Event("bonus", float(m.group(1)), float(m.group(2))))
    for m in _RIGHTS.finditer(s):
        a, b = float(m.group(1)), float(m.group(2))
        tail = s[m.end() :]
        price: float | None = None
        pm = _PREMIUM.search(tail)
        if pm:
            price = float(pm.group(1)) + (face_value or 0.0)
        else:
            am = _AT_PRICE.search(tail)
            if am:
                price = float(am.group(1))
        events.append(Event("rights", a, b, price))
    if not any(k in low for k in ("split", "splt", "consolidat", "sub-div", "subdiv")):
        for m in _DIV.finditer(s):
            amount = float(m.group(1))
            if m.group(2):  # "Dividend 50%" = percent of face value
                if face_value is None:
                    continue
                amount = amount / 100.0 * face_value
            if amount > 0:
                events.append(Event("dividend", amount=amount))
    if "demerger" in low or "spin off" in low or "spin-off" in low:
        events.append(Event("demerger"))
    elif not events and any(k in low for k in _SCHEME_WORDS):
        # (a scheme that is only a bonus/split was already captured above)
        events.append(Event("scheme_of_arrangement"))
    if "capital reduction" in low or "reduction of capital" in low:
        events.append(Event("capital_reduction"))
    return events

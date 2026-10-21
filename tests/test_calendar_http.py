from __future__ import annotations

import datetime as dt

import pytest
import requests

import bhavpy as bp
from bhavpy import calendar, http
from bhavpy.errors import BlockedError, NotAvailable

from .conftest import FakeServer


def test_bundled_calendar_is_sane() -> None:
    cal = calendar._bundled()
    assert set(cal["kind"]) == {"holiday", "special_session"}
    hol = cal[cal["kind"] == "holiday"]
    assert (dt.date.fromisoformat(d).weekday() < 5 for d in hol["date"])
    assert "2024-03-02" in set(cal[cal["kind"] == "special_session"]["date"])  # Saturday DR session
    assert len(hol) > 200


def test_trading_days_2026(offline_http: FakeServer) -> None:
    days = bp.trading_days("2026-01-23", "2026-01-30")
    s = [d.strftime("%Y-%m-%d") for d in days]
    assert "2026-01-26" not in s  # Republic Day
    assert "2026-01-24" not in s and "2026-01-25" not in s  # weekend
    assert "2026-01-27" in s
    assert bp.is_trading_day("2026-01-27") and not bp.is_trading_day("2026-01-26")
    assert bp.next_trading_day("2026-01-23").strftime("%Y-%m-%d") == "2026-01-27"


def test_special_sessions_are_trading_days(offline_http: FakeServer) -> None:
    assert bp.is_trading_day("2024-03-02")
    assert bp.is_trading_day("2025-02-01")  # Union Budget Saturday


class _Resp:
    def __init__(self, code: int, body: bytes, ctype: str = "text/csv") -> None:
        self.status_code, self.content, self.headers = code, body, {"Content-Type": ctype}


def _patch(monkeypatch: pytest.MonkeyPatch, responses: list[_Resp]) -> list[str]:
    calls: list[str] = []

    def fake_get(self: requests.Session, url: str, **kw: object) -> _Resp:
        calls.append(url)
        return responses.pop(0) if len(responses) > 1 else responses[0]

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    http.reset()
    return calls


def test_http_404_is_not_available(monkeypatch: pytest.MonkeyPatch, tmp_cache: object) -> None:
    _patch(monkeypatch, [_Resp(404, b"")])
    with pytest.raises(NotAvailable):
        http.get("https://nsearchives.nseindia.com/x.csv", expect="csv")


def test_http_retries_5xx_then_succeeds(monkeypatch: pytest.MonkeyPatch, tmp_cache: object) -> None:
    calls = _patch(monkeypatch, [_Resp(503, b""), _Resp(502, b""), _Resp(200, b"a,b\n1,2\n")])
    assert http.get("https://nsearchives.nseindia.com/x.csv", expect="csv") == b"a,b\n1,2\n"
    assert len(calls) == 3


def test_http_html_instead_of_json_is_blocked(monkeypatch: pytest.MonkeyPatch, tmp_cache: object) -> None:
    _patch(monkeypatch, [_Resp(200, b"<html>Access Denied</html>", "text/html")])
    with pytest.raises(BlockedError, match="does not bypass"):
        http.get("https://www.nseindia.com/api/x", expect="json")


def test_http_offline(monkeypatch: pytest.MonkeyPatch, tmp_cache: object) -> None:
    bp.configure(offline=True)
    try:
        with pytest.raises(NotAvailable, match="offline"):
            http.get("https://nsearchives.nseindia.com/x.csv")
    finally:
        bp.configure(offline=False)


def test_rate_limiter_spaces_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(http.time, "sleep", lambda s: slept.append(s))
    lim = http._RateLimiter()
    bp.configure(rate=2)
    try:
        for _ in range(3):
            lim.wait("example.com")
    finally:
        bp.configure(rate=3)
    assert len(slept) == 2 and slept[-1] == pytest.approx(1.0, abs=0.05)


def test_configure_rejects_unknown() -> None:
    with pytest.raises(TypeError):
        bp.configure(nope=1)

"""Polite HTTP: per-host rate limit, retries with backoff, clear errors.

All network access in bhavpy goes through :func:`get`. It never solves bot checks or
CAPTCHAs: if the exchange answers with one, a :class:`~bhavpy.errors.BlockedError` is
raised and the caller decides what to do.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from urllib.parse import urlparse

import requests

from .config import settings
from .errors import BlockedError, NetworkError, NotAvailable

log = logging.getLogger("bhavpy")

_REFERERS = {
    "nsearchives.nseindia.com": "https://www.nseindia.com/",
    "archives.nseindia.com": "https://www.nseindia.com/",
    "www.nseindia.com": "https://www.nseindia.com/",
    "www.niftyindices.com": "https://www.niftyindices.com/",
    "www.bseindia.com": "https://www.bseindia.com/",
    "api.bseindia.com": "https://www.bseindia.com/",
}

#: Markers of an HTML error/bot page served where data was expected.
_BLOCK_MARKERS = (b"Access Denied", b"captcha", b"Request Rejected", b"bot-check", b"_abck")


class _RateLimiter:
    """Minimum spacing between requests to one host, shared by all threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}

    def wait(self, host: str) -> None:
        rate = max(settings.rate, 0.01)
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next.get(host, now))
            self._next[host] = slot + 1.0 / rate
        delay = slot - now
        if delay > 0:
            time.sleep(delay)


_limiter = _RateLimiter()
_local = threading.local()
_warmed: set[str] = set()


def _session() -> requests.Session:
    s: requests.Session | None = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }
        )
        _local.session = s
    return s


def reset() -> None:
    """Drop pooled sessions (called when settings change)."""
    _local.__dict__.clear()
    _warmed.clear()


def _looks_blocked(resp: requests.Response, expect: str) -> bool:
    ctype = resp.headers.get("Content-Type", "")
    head = resp.content[:4000]
    if expect in ("json", "csv", "zip") and "text/html" in ctype:
        return True
    return any(m.lower() in head.lower() for m in _BLOCK_MARKERS) and expect != "html"


def _warm_up(host: str) -> None:
    """Visit the site's home page once so the session holds the cookies a browser would."""
    if host in _warmed:
        return
    _warmed.add(host)
    home = _REFERERS.get(host)
    if not home:
        return
    try:
        _limiter.wait(urlparse(home).netloc)
        _session().get(home, timeout=settings.timeout)
    except requests.RequestException:  # pragma: no cover - best effort
        pass


def get(
    url: str,
    *,
    expect: str = "any",
    params: dict[str, str] | None = None,
    referer: str | None = None,
) -> bytes:
    """GET ``url`` and return the body.

    ``expect`` is one of ``"csv" | "zip" | "json" | "html" | "any"`` and is used to spot
    error pages that come back with HTTP 200.

    Raises :class:`NotAvailable` on 404, :class:`BlockedError` on 401/403/429 or a
    bot page (after one cookie warm-up and the normal retries), and
    :class:`NetworkError` when retries are exhausted.
    """
    if settings.offline:
        raise NotAvailable(f"offline mode: not fetching {url}")
    host = urlparse(url).netloc
    headers = {"Referer": referer or _REFERERS.get(host, f"https://{host}/")}
    if expect == "json":
        headers["Accept"] = "application/json, text/plain, */*"
    last_exc: Exception | None = None
    blocked_reason = ""
    for attempt in range(settings.retries + 1):
        if attempt:
            time.sleep(min(30.0, (2**attempt) * 0.75 + random.uniform(0, 0.5)))
        _limiter.wait(host)
        try:
            resp = _session().get(url, params=params, headers=headers, timeout=settings.timeout)
        except requests.RequestException as exc:
            last_exc = exc
            log.debug("network error on %s (attempt %d): %s", url, attempt + 1, exc)
            continue
        code = resp.status_code
        if code == 404:
            raise NotAvailable(f"404 Not Found: {url}")
        if code in (401, 403) or (code == 200 and _looks_blocked(resp, expect)):
            blocked_reason = f"HTTP {code}" + (" with an HTML/bot page" if code == 200 else "")
            if host.endswith("nseindia.com") and host not in _warmed:
                _warm_up(host)
                continue
            if attempt >= 1:
                break
            continue
        if code == 429 or code >= 500:
            blocked_reason = f"HTTP {code}"
            last_exc = None
            log.debug("server said %s for %s; backing off", code, url)
            continue
        if code >= 400:
            raise NotAvailable(f"HTTP {code}: {url}")
        return resp.content
    if blocked_reason:
        raise BlockedError(
            f"{host} refused the request ({blocked_reason}) for {url}. "
            "bhavpy does not bypass blocks; wait and retry, lower bhavpy.configure(rate=...), "
            "or prefer archive-based functions."
        )
    raise NetworkError(f"giving up on {url} after {settings.retries + 1} attempts: {last_exc}")


def get_json(url: str, params: dict[str, str] | None = None, referer: str | None = None) -> object:
    import json

    from .errors import FormatChanged

    body = get(url, expect="json", params=params, referer=referer)
    try:
        return json.loads(body.decode("utf-8-sig"))
    except ValueError as exc:
        raise FormatChanged(f"expected JSON from {url}, got: {body[:200]!r}") from exc

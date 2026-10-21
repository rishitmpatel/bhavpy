"""Shared fixtures. Unit tests never touch the network: ``offline_http`` serves recorded
files from tests/fixtures by URL, and anything unrecognised fails loudly."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

import bhavpy
from bhavpy import cache, http
from bhavpy.errors import NotAvailable

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


#: URL regex -> fixture file (or callable(match, params) -> file name).
ROUTES: list[tuple[str, object]] = [
    (r"content/cm/(BhavCopy_NSE_CM_0_0_0_\d{8}_F_0000\.csv\.zip)$", 1),
    (r"content/fo/(BhavCopy_NSE_FO_0_0_0_\d{8}_F_0000\.csv\.zip)$", 1),
    (r"historical/EQUITIES/\d{4}/[A-Z]{3}/(cm\w+bhav\.csv\.zip)$", 1),
    (r"historical/DERIVATIVES/\d{4}/[A-Z]{3}/(fo\w+bhav\.csv\.zip)$", 1),
    (r"content/indices/(ind_close_all_\d{8}\.csv)$", 1),
    (r"BhavCopy/Equity/(BhavCopy_BSE_CM_0_0_0_\d{8}_F_0000\.CSV)$", 1),
    (r"BhavCopy/Equity/(EQ_ISINCODE_\d{6}\.zip)$", 1),
    (
        r"content/equities/(EQUITY_L\.csv|symbolchange\.csv|namechange\.csv|delisted\.csv|bulk\.csv|block\.csv)$",
        1,
    ),
    (r"emerge/corporates/content/(SME_EQUITY_L\.csv)$", 1),
    (r"IndexConstituent/(ind_\w+list\.csv)$", 1),
    (r"content/fo/(fo_mktlots\.csv)$", 1),
    (r"api/fiidiiTradeReact$", "fiidiiTradeReact.json"),
    (r"api/option-chain-contract-info$", "option-chain-contract-info-NIFTY.json"),
    (r"api/option-chain-v3$", "option-chain-v3-NIFTY.json"),
    (r"api/historicalOR/bulk-block-short-deals$", "bulk_deals.json"),
]


class FakeServer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        *,
        expect: str = "any",
        params: dict[str, str] | None = None,
        referer: str | None = None,
    ) -> bytes:
        self.calls.append(url)
        if url.endswith("api/holiday-master"):
            year = (params or {}).get("year")
            name = f"holiday-master-{year}.json"
            if not (FIXTURES / name).exists():
                raise NotAvailable(name)
            return fixture_bytes(name)
        if url.endswith("api/corporates-corporateActions"):
            name = f"corporate-actions-{(params or {}).get('symbol')}.json"
            return fixture_bytes(name) if (FIXTURES / name).exists() else b"[]"
        for pattern, target in ROUTES:
            m = re.search(pattern, url)
            if m:
                name = m.group(1) if target == 1 else str(target)
                if not (FIXTURES / name).exists():
                    raise NotAvailable(f"404 (no fixture): {url}")
                return fixture_bytes(name)
        raise AssertionError(f"unit test tried to fetch an unexpected URL: {url}")


@pytest.fixture
def tmp_cache(tmp_path: Path) -> Iterator[Path]:
    old = bhavpy.settings.cache_dir
    bhavpy.configure(cache_dir=tmp_path, progress=False, offline=False)
    yield tmp_path
    cache.reset()
    bhavpy.configure(cache_dir=old)


@pytest.fixture
def offline_http(monkeypatch: pytest.MonkeyPatch, tmp_cache: Path) -> FakeServer:
    server = FakeServer()
    monkeypatch.setattr(http, "get", server.get)
    from bhavpy import symbols

    symbols._chain_cached.cache_clear()
    return server

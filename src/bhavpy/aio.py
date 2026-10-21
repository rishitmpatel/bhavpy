"""Async wrappers: ``await bhavpy.aio.history("TCS", "2020-01-01")``.

Each call runs the sync implementation in a worker thread (``asyncio.to_thread``), so
the event loop stays free while downloads happen. The global per-host rate limit still
applies across concurrent calls, so gathering many requests stays polite.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import pandas as pd

from . import equity, flows, fno, indices

T = TypeVar("T")


def _wrap(fn: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    @functools.wraps(fn)
    async def runner(*args: Any, **kwargs: Any) -> T:
        return await asyncio.to_thread(fn, *args, **kwargs)

    return runner


history: Callable[..., Awaitable[pd.DataFrame]] = _wrap(equity.history)
factors: Callable[..., Awaitable[pd.DataFrame]] = _wrap(equity.factors)
index_history: Callable[..., Awaitable[pd.DataFrame]] = _wrap(equity.index_history)
market: Callable[..., Awaitable[pd.DataFrame]] = _wrap(equity.market)
constituents: Callable[..., Awaitable[pd.DataFrame]] = _wrap(indices.constituents)
option_chain: Callable[..., Awaitable[pd.DataFrame]] = _wrap(fno.option_chain)
fii_dii: Callable[..., Awaitable[pd.DataFrame]] = _wrap(flows.fii_dii)

__all__ = [
    "constituents",
    "factors",
    "fii_dii",
    "history",
    "index_history",
    "market",
    "option_chain",
]

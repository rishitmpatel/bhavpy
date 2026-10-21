"""bhavpy - Indian stock market data (NSE + BSE) from public exchange archives.

Quick start::

    import bhavpy as bp

    df = bp.history("RELIANCE", "2015-01-01")          # raw + split/bonus-adjusted OHLCV
    bp.factors("RELIANCE", "2015-01-01")                # every adjustment, auditable
    bp.history("NIFTY 50", "2020-01-01")                # index history
    bp.constituents("NIFTY 50", as_of="2019-06-01")     # point-in-time members
    bp.option_chain("NIFTY")                            # live option chain snapshot

Not affiliated with NSE or BSE. Data is for personal/research use; you are responsible
for following the exchanges' terms of use. Nothing here is investment advice.
"""

from __future__ import annotations

from . import bse, calendar, flows, fno, indices, symbols
from ._version import __version__
from .adjust import corporate_actions
from .calendar import holidays, is_trading_day, next_trading_day, previous_trading_day, trading_days
from .config import configure, settings
from .equity import factors, history, index_history, market, universe
from .errors import (
    BhavpyError,
    BlockedError,
    FormatChanged,
    NetworkError,
    NotAvailable,
    SymbolNotFound,
)
from .flows import block_deals, bulk_deals, fii_dii, fii_dii_history
from .fno import expiries, expiry_calendar, futures, lot_sizes, option_chain
from .indices import constituents
from .symbols import equity_list, resolve, symbol_chain
from .update import update

__all__ = [
    "BhavpyError",
    "BlockedError",
    "FormatChanged",
    "NetworkError",
    "NotAvailable",
    "SymbolNotFound",
    "__version__",
    "block_deals",
    "bse",
    "bulk_deals",
    "calendar",
    "configure",
    "constituents",
    "corporate_actions",
    "equity_list",
    "expiries",
    "expiry_calendar",
    "factors",
    "fii_dii",
    "fii_dii_history",
    "flows",
    "fno",
    "futures",
    "history",
    "holidays",
    "index_history",
    "indices",
    "is_trading_day",
    "lot_sizes",
    "market",
    "next_trading_day",
    "option_chain",
    "previous_trading_day",
    "resolve",
    "settings",
    "symbol_chain",
    "symbols",
    "trading_days",
    "universe",
    "update",
]

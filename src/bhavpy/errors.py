"""Exception hierarchy.

Every error raised by bhavpy derives from :class:`BhavpyError`, so callers can
catch one type. The subclasses say *why* something failed, because the fix is
different in each case: wait and retry, update the library, or check the input.
"""

from __future__ import annotations


class BhavpyError(Exception):
    """Base class for all bhavpy errors."""


class NotAvailable(BhavpyError):
    """The exchange has no file for this request (holiday, not yet published, or before
    the archive starts). Not a bug: the data simply does not exist at the source."""


class BlockedError(BhavpyError):
    """The exchange refused the request (HTTP 401/403/429, or a bot-check page).

    bhavpy never tries to get around such blocks. Wait a while, lower the request
    rate (``bhavpy.configure(rate=...)``), or use the archive-based functions, which
    are rarely blocked.
    """


class FormatChanged(BhavpyError):
    """A file or JSON response no longer has the shape bhavpy expects.

    This usually means the exchange changed a URL or column layout. Please open an
    issue with the message text; the daily live test suite normally catches these
    within a day.
    """


class SymbolNotFound(BhavpyError):
    """The symbol could not be resolved, even through rename/delisting history."""


class NetworkError(BhavpyError):
    """The request failed after all retries (timeouts, DNS, connection resets)."""

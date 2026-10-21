"""Runtime settings: cache location, politeness limits, timeouts.

Change them with :func:`bhavpy.configure` or environment variables
(``BHAVPY_CACHE_DIR``, ``BHAVPY_RATE``, ``BHAVPY_OFFLINE``).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from ._version import __version__

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def _default_cache_dir() -> Path:
    env = os.environ.get("BHAVPY_CACHE_DIR")
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "bhavpy"


@dataclass
class Settings:
    cache_dir: Path = field(default_factory=_default_cache_dir)
    #: Max requests per second per host. Archives tolerate a few per second; keep it modest.
    rate: float = float(os.environ.get("BHAVPY_RATE", "3"))
    #: Parallel downloads during bulk backfills (still bounded by ``rate``).
    workers: int = 3
    timeout: float = 30.0
    retries: int = 4
    #: Browser-like UA (the archives reject bare library UAs) plus an honest product token.
    user_agent: str = f"{_BROWSER_UA} bhavpy/{__version__}"
    #: Never touch the network; serve only from cache.
    offline: bool = os.environ.get("BHAVPY_OFFLINE", "") not in ("", "0", "false")
    #: Show a progress line on stderr during multi-day downloads.
    progress: bool = True
    #: Hours after which "today" style live snapshots (lists, constituents, corp actions) are refetched.
    ttl_hours: float = 20.0


settings = Settings()


def configure(**kwargs: Any) -> Settings:
    """Change settings, e.g. ``bhavpy.configure(cache_dir="~/data/bhavpy", rate=2)``.

    Returns the active :class:`Settings`.
    """
    names = {f.name for f in fields(Settings)}
    for key, value in kwargs.items():
        if key not in names:
            raise TypeError(f"unknown setting {key!r}; valid: {sorted(names)}")
        if key == "cache_dir":
            value = Path(value).expanduser()
        setattr(settings, key, value)
    if "cache_dir" in kwargs:
        from . import cache

        cache.reset()
    if "rate" in kwargs or "user_agent" in kwargs or "timeout" in kwargs:
        from . import http

        http.reset()
    return settings

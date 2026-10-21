"""Shared plumbing for sources: the daily-archive base class and CSV helpers."""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Iterable

import pandas as pd

from ..errors import FormatChanged


class DailySource(ABC):
    """A source that publishes one file per trading day (bhavcopies, index closes)."""

    #: Key used in the cache's fetch log.
    dataset: str
    #: SQLite table holding parsed rows.
    table: str
    #: DDL for ``table``.
    ddl: str
    #: Column order written to ``table``.
    columns: tuple[str, ...]
    #: Earliest day the archive is known to have.
    first_date: dt.date
    #: File kind for error-page detection ("zip" or "csv").
    expect: str = "csv"
    #: Store ``date`` as an integer YYYYMMDD (smaller, faster) instead of ISO text.
    int_date: bool = False
    #: Columns stored as integer paise (price * 100) to keep the cache compact.
    paise_columns: tuple[str, ...] = ()
    #: Columns stored as rounded integers.
    int_columns: tuple[str, ...] = ()

    def for_storage(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rows (and representation) written to the cache table."""
        out = df.loc[:, list(self.columns)].copy()
        if self.int_date:
            out["date"] = out["date"].str.replace("-", "", regex=False).astype("int64")
        for c in self.paise_columns:
            out[c] = (pd.to_numeric(out[c], errors="coerce") * 100).round().astype("Int64")
        for c in self.int_columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").round().astype("Int64")
        return out

    def from_storage(self, df: pd.DataFrame) -> pd.DataFrame:
        """Inverse of :meth:`for_storage` for rows read back from the cache."""
        if df.empty:
            return df
        if self.int_date:
            d = df["date"].astype("int64").astype(str)
            df["date"] = d.str[:4] + "-" + d.str[4:6] + "-" + d.str[6:]
        for c in self.paise_columns:
            df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
        for c in self.int_columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
        return df

    def date_key(self, day: dt.date) -> object:
        return int(day.strftime("%Y%m%d")) if self.int_date else day.isoformat()

    @abstractmethod
    def urls(self, day: dt.date) -> list[str]:
        """Candidate URLs for ``day``, most likely first."""

    @abstractmethod
    def parse(self, raw: bytes, day: dt.date) -> pd.DataFrame:
        """Parse a downloaded file into canonical columns (must include ``date``)."""

    def expect_for(self, url: str) -> str:
        return "zip" if url.lower().endswith(".zip") else "csv"


def unzip_first(raw: bytes, suffix: str = ".csv") -> bytes:
    """Return the first member of a zip whose name ends with ``suffix`` (case-insensitive)."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(suffix)]
            if not names:
                raise FormatChanged(f"zip has no {suffix} member: {zf.namelist()}")
            return zf.read(names[0])
    except zipfile.BadZipFile as exc:
        raise FormatChanged(f"not a zip file (first bytes {raw[:60]!r})") from exc


def maybe_unzip(raw: bytes, suffix: str = ".csv") -> bytes:
    return unzip_first(raw, suffix) if raw[:2] == b"PK" else raw


def read_csv(raw: bytes, **kwargs: object) -> pd.DataFrame:
    """Read CSV bytes; strip whitespace from headers and string cells; drop empty columns."""
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, encoding="latin-1", **kwargs)  # type: ignore[call-overload]
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise FormatChanged(f"could not parse CSV: {exc}") from exc
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, [c for c in df.columns if c and not c.startswith("Unnamed")]]
    for col in df.columns:
        df[col] = df[col].str.strip()
    return df


def require(df: pd.DataFrame, cols: Iterable[str], what: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise FormatChanged(
            f"{what}: expected columns {missing} not found; got {list(df.columns)}. "
            "The exchange probably changed the file layout."
        )


def num(s: pd.Series, scale: float = 1.0) -> pd.Series:
    """Parse numbers like '1,234.50', '-', '' -> float (NaN for blanks)."""
    cleaned = s.astype(str).str.replace(",", "", regex=False).str.strip()
    cleaned = cleaned.mask(cleaned.isin(["", "-", "NA", "nan", "None"]))
    out = pd.to_numeric(cleaned, errors="coerce")
    return out * scale if scale != 1.0 else out


def dates(s: pd.Series, fmt: str | None = None) -> pd.Series:
    """Parse a column of dates to ISO strings (YYYY-MM-DD); unparseable -> None."""
    s = s.astype(str).str.strip()
    if fmt is not None:
        parsed = pd.to_datetime(s, format=fmt, errors="coerce")
    else:
        best = None
        for f in _DATE_FORMATS:
            cand = pd.to_datetime(s, format=f, errors="coerce")
            if best is None or cand.notna().sum() > best.notna().sum():
                best = cand
            if cand.notna().all():
                break
        assert best is not None
        parsed = best
    return parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), None)


_DATE_FORMATS = ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%B-%Y", "%d %b %Y")

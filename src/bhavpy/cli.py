"""Command line: ``bhavpy download RELIANCE --from 2015-01-01 --adjusted -o reliance.csv``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from . import __version__, cache
from .config import configure

DISCLAIMER = (
    "bhavpy is not affiliated with NSE or BSE. Data is for personal/research use; you are "
    "responsible for following the exchanges' terms of use. Not investment advice."
)


def _write(df: pd.DataFrame, out: str | None) -> None:
    if df.index.name or isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()
    for c in df.columns:
        if isinstance(df[c].dtype, pd.DatetimeTZDtype):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
    if out is None or out == "-":
        df.to_csv(sys.stdout, index=False)
        return
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    suffix = p.suffix.lower()
    if suffix == ".parquet":
        df.to_parquet(p, index=False)
    elif suffix in (".json", ".jsonl"):
        df.to_json(p, orient="records", lines=suffix == ".jsonl", indent=None if suffix == ".jsonl" else 1)
    elif suffix in (".xlsx",):
        df.to_excel(p, index=False)
    else:
        df.to_csv(p, index=False)
    print(f"wrote {len(df)} rows to {p}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bhavpy", description="NSE/BSE market data from public archives. " + DISCLAIMER
    )
    p.add_argument("--version", action="version", version=f"bhavpy {__version__}")
    p.add_argument("--cache-dir", help="cache directory (default: platform cache dir or $BHAVPY_CACHE_DIR)")
    p.add_argument("--rate", type=float, help="max requests per second per host (default 3)")
    p.add_argument("--offline", action="store_true", help="serve from cache only; no network")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress output")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="daily history for a stock or index")
    d.add_argument("symbol")
    d.add_argument("--from", dest="start", help="start date (default: 1 year ago)")
    d.add_argument("--to", dest="end", help="end date (default: today)")
    d.add_argument(
        "--adjusted", nargs="?", const="split", choices=["split", "total"],
        help="add adjusted columns (split = splits/bonus/rights; total = also dividends)",
    )  # fmt: skip
    d.add_argument("--only-adjusted", action="store_true", help="output only adjusted OHLCV columns")
    d.add_argument("-o", "--output", help="output file (.csv, .parquet, .json, .xlsx); default stdout")

    f = sub.add_parser("factors", help="corporate-action adjustment factors for a stock")
    f.add_argument("symbol")
    f.add_argument("--from", dest="start")
    f.add_argument("--to", dest="end")
    f.add_argument("--total", action="store_true", help="include dividends")
    f.add_argument("-o", "--output")

    u = sub.add_parser("update", help="refresh the cache (only fetches missing days)")
    u.add_argument("--from", dest="start", help="backfill from this date (first run)")
    u.add_argument("--indices-only", action="store_true", help="skip the equity bhavcopy")

    c = sub.add_parser("constituents", help="index members (current or --as-of)")
    c.add_argument("index", nargs="?", default="NIFTY 50")
    c.add_argument("--as-of")
    c.add_argument("-o", "--output")

    oc = sub.add_parser("chain", help="live option chain snapshot")
    oc.add_argument("symbol", nargs="?", default="NIFTY")
    oc.add_argument("--expiry")
    oc.add_argument("-o", "--output")

    m = sub.add_parser("market", help="whole-market bhavcopy for a day")
    m.add_argument("--date")
    m.add_argument("--exchange", choices=["nse", "bse"], default="nse")
    m.add_argument("-o", "--output")

    h = sub.add_parser("holidays", help="trading holidays for a year")
    h.add_argument("year", nargs="?", type=int)

    s = sub.add_parser("symbol", help="resolve a symbol: current ticker, ISIN, rename history")
    s.add_argument("symbol")

    fl = sub.add_parser("flows", help="FII/DII flows (latest, or --history from cache)")
    fl.add_argument("--history", action="store_true")
    fl.add_argument("-o", "--output")

    dl = sub.add_parser("deals", help="bulk or block deals")
    dl.add_argument("kind", choices=["bulk", "block"])
    dl.add_argument("--from", dest="start")
    dl.add_argument("--to", dest="end")
    dl.add_argument("-o", "--output")

    ca = sub.add_parser("cache", help="cache info / clear")
    ca.add_argument("action", choices=["info", "clear", "path", "vacuum"])
    ca.add_argument("--dataset", help="with clear: only forget this dataset's fetch log")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(message)s"
    )
    opts: dict[str, object] = {}
    if args.cache_dir:
        opts["cache_dir"] = args.cache_dir
    if args.rate:
        opts["rate"] = args.rate
    if args.offline:
        opts["offline"] = True
    if args.quiet:
        opts["progress"] = False
    if opts:
        configure(**opts)

    import bhavpy as bp

    try:
        if args.cmd == "download":
            df = bp.history(args.symbol, args.start, args.end, adjust=args.adjusted)
            if args.only_adjusted and args.adjusted:
                cols = ["adj_open", "adj_high", "adj_low", "adj_close", "adj_volume"]
                df = df[cols].rename(columns=lambda c: c.removeprefix("adj_"))
            _write(df, args.output)
        elif args.cmd == "factors":
            _write(
                bp.factors(args.symbol, args.start, args.end, adjust="total" if args.total else "split"),
                args.output,
            )
        elif args.cmd == "update":
            print(json.dumps(bp.update(args.start, indices_only=args.indices_only), indent=2, default=str))
        elif args.cmd == "constituents":
            _write(bp.constituents(args.index, args.as_of), args.output)
        elif args.cmd == "chain":
            df = bp.option_chain(args.symbol, args.expiry)
            print(
                f"# {df.attrs.get('symbol')} @ {df.attrs.get('timestamp')} "
                f"underlying {df.attrs.get('underlying_price')}",
                file=sys.stderr,
            )
            _write(df, args.output)
        elif args.cmd == "market":
            df = bp.market(args.date) if args.exchange == "nse" else bp.bse.bhavcopy(args.date)
            _write(df, args.output)
        elif args.cmd == "holidays":
            _write(bp.holidays(args.year), None)
        elif args.cmd == "symbol":
            print(json.dumps(bp.symbols.info(args.symbol), indent=2, default=str))
        elif args.cmd == "flows":
            _write(bp.fii_dii_history() if args.history else bp.fii_dii(), args.output)
        elif args.cmd == "deals":
            fn = bp.bulk_deals if args.kind == "bulk" else bp.block_deals
            _write(fn(args.start, args.end), args.output)
        elif args.cmd == "cache":
            if args.action == "path":
                print(cache.path())
            elif args.action == "info":
                print(json.dumps(cache.info(), indent=2))
            elif args.action == "vacuum":
                cache.vacuum()
                print(json.dumps(cache.info(), indent=2))
            else:
                cache.clear(args.dataset)
                print("cleared" + (f" fetch log for {args.dataset}" if args.dataset else f" {cache.path()}"))
    except bp.BhavpyError as exc:
        print(f"bhavpy: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

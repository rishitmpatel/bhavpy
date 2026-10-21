"""Check corporate-action adjustment across an index's members.

    python scripts/validate_adjustment.py "NIFTY 500" 2015-01-01

For every member it reports the events applied, price-check mismatches, unexplained
gaps, and the largest daily move in raw vs adjusted closes. A split/bonus/rights date
should never be the largest adjusted move. Needs a filled cache (``bhavpy update``).
"""

from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd

import bhavpy as bp


def _days(ev: pd.DataFrame, mask: pd.Series) -> str:
    return ",".join(ev.loc[mask, "ex_date"].dt.strftime("%Y-%m-%d").unique())


def main() -> None:
    index = sys.argv[1] if len(sys.argv) > 1 else "NIFTY 50"
    start = sys.argv[2] if len(sys.argv) > 2 else "2015-01-01"
    bp.configure(progress=False)
    rows = []
    for sym in bp.constituents(index)["symbol"]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                df = bp.history(sym, start, None)
            except bp.BhavpyError as exc:
                print(f"skip {sym}: {exc}")
                continue
        ev = df.attrs["events"]
        raw = np.log(df["close"] / df["close"].shift()).abs()
        adj = np.log(df["adj_close"] / df["adj_close"].shift()).abs()
        rows.append(
            {
                "symbol": sym,
                "days": len(df),
                "applied": int(ev["applied"].sum()),
                "mismatch": _days(ev, ev["check"] == "mismatch"),
                "gaps": _days(ev, ev["kind"] == "unexplained_gap"),
                "max_raw_move": round(float(np.expm1(raw.max())), 3),
                "max_adj_move": round(float(np.expm1(adj.max())), 3),
                "on": adj.idxmax().strftime("%Y-%m-%d"),
            }
        )
    out = pd.DataFrame(rows).sort_values("max_adj_move", ascending=False)
    pd.set_option("display.width", 200)
    print(out.head(30).to_string(index=False))
    print(
        f"\n{len(out)} stocks, {out['applied'].sum()} events applied, "
        f"{(out['mismatch'] != '').sum()} with mismatches, {(out['gaps'] != '').sum()} with unexplained gaps"
    )


if __name__ == "__main__":
    main()

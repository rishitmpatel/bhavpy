# Roadmap

## v0.2 (next)

* **Delivery data** — `sec_bhavdata_full` (2020+): deliverable quantity and %.
* **NIFTY 50 history back to 2005**, and bundled change logs for NIFTY BANK / NIFTY NEXT 50.
* **Export** — `bhavpy export DIR` writing year-partitioned Parquet from the cache.
* **Demerger handling** — use NSE's announced cost-of-acquisition split (when published)
  instead of the ex-day price estimate.
* **BSE corporate actions** and adjusted BSE series; SENSEX/BSE index closes.

## v0.3

* **Native async** HTTP (httpx) for faster first-time backfills within the same politeness limits.
* **Expiry calendar rules** for future dates (weekly/monthly expiry-day rules by period),
  cross-checked against the F&O archive.
* **Index changes from NSE Indices press releases** parsed automatically, so point-in-time
  constituents extend themselves for all broad indices.
* **Data-quality report** per symbol: gaps, suspensions, series changes, unexplained jumps.

## Later

* Intraday-free extras from public archives: market-wide position limits, ban list,
  participant-wise OI, short selling, SLB.
* Total-return index (TRI) history.
* `pandas`-free core with optional Polars output.

Have a source in mind? Open a *Feature or new data source* issue with the public URL.

# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-21

First release.

- Daily OHLCV for every NSE stock from the official bhavcopy archive (1994 → today), both
  legacy and UDiFF (July 2024+) formats.
- Corporate-action adjustment (splits, consolidations, bonuses, rights; dividends with
  `adjust="total"`) from NSE's corporate-actions feed, price-checked, with a per-event
  factor table (`bhavpy.factors`).
- Symbol master with renames and delistings; old tickers resolve and history is stitched.
- Index history (2012 → today) with historic index names mapped; current constituents for
  27 indices; point-in-time NIFTY 50 from 2016.
- F&O bhavcopy, continuous futures, live option chain, lot sizes, expiries.
- Trading calendar (holidays 2005+, special sessions), FII/DII flows, bulk/block deals.
- BSE bhavcopy (2017 → today) and NSE↔BSE ISIN mapping.
- SQLite cache with incremental `bhavpy update`, offline mode, polite rate limiting.
- CLI, async wrappers, typed API; daily live test suite on GitHub Actions.

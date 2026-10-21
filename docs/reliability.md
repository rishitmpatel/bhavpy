# Reliability: what is solid, what is fragile

| Feature | Source | Rating | Why |
|---|---|---|---|
| Equity OHLCV history | NSE bhavcopy archive (1994 →) | **Solid** | Static files; URLs unchanged for years except the July 2024 UDiFF switch, which bhavpy handles. Cached forever once downloaded. |
| Index history | NSE `ind_close_all` archive (2012-03 →) | **Solid** | Static daily files. Old index names are mapped. *Gap:* no pre-2012 index history in this archive. |
| Symbol master, renames, delistings | NSE CSV files | **Solid** | Plain CSVs; cached; stale copy used if a refresh fails. |
| F&O bhavcopy, futures, lot sizes | NSE archives | **Solid** | Static files. |
| BSE bhavcopy | BSE download files (2017 →) | **Good** | Static files, but BSE returns its HTML shell (HTTP 200) for missing days; bhavpy detects that. Pre-2017 files are no longer served. |
| Current index constituents | niftyindices.com CSVs | **Good** | Static per-index files; file codes could be renamed. |
| Point-in-time NIFTY 50 | bundled change log since 2016 | **Good** | Validated every day: reconstructed members must have traded. Must be extended when NSE changes the index (twice a year); a test fails if today's list stops matching. |
| Point-in-time for other indices | local snapshots | **Limited** | Only from your first `bhavpy update`; NSE publishes no free history. |
| Adjustment ratios | NSE corporate-actions JSON | **Good** | JSON endpoint (could change), but cached per symbol, every record is price-checked, and if the feed is unreachable bhavpy falls back to inferring splits/bonuses from price gaps. Demergers are not adjusted automatically. |
| Holidays | NSE holiday API (2011 →) + bundled calendar (2005 →) | **Solid** | Works offline from the bundled file. |
| Option chain | NSE live JSON (`option-chain-v3`) | **Fragile** | Live website endpoint; NSE has retired previous versions (`option-chain-indices` now 404) and may add bot protection. Only snapshot; no history. |
| FII/DII | NSE live JSON | **Fragile** | Latest day only; history exists only if you run `update` daily. |
| Bulk/block deal history | NSE live JSON | **Fragile** | Website endpoint; the daily CSV archive is used for today's deals as a fallback source. |

## What happens when something breaks

* bhavpy raises `FormatChanged` with the URL and the columns it saw, instead of returning
  wrong data.
* The [live workflow](https://github.com/rishitmpatel/bhavpy/actions/workflows/live.yml)
  runs every day and opens an issue labelled `source-broken` within 24 hours.
* The fix is one module in `src/bhavpy/sources/`; see CONTRIBUTING.md.
* Cached data keeps working (`bp.configure(offline=True)`).

## Politeness

* At most 3 requests/s per host by default (`bp.configure(rate=...)`), 3 parallel workers.
* Retries with exponential backoff and jitter on 429/5xx/connection errors.
* An honest `bhavpy/<version>` token in the User-Agent.
* Each archive file is downloaded once; days with no file (holidays) are remembered.
* bhavpy never solves CAPTCHAs, never retries around a 403 more than once, and never uses
  logins or paid APIs.

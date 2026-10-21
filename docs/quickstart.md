# Quickstart

## Install

```bash
pip install bhavpy            # pandas + requests only
pip install "bhavpy[plot]"    # + matplotlib/scipy for the cookbook plots
```

Python 3.10–3.13 on Linux, macOS and Windows.

## Stock history

```python
import bhavpy as bp

df = bp.history("TCS", "2020-01-01", "2024-12-31")
df.columns
# symbol series isin open high low close last prev_close volume turnover trades
# adj_open adj_high adj_low adj_close adj_last adj_prev_close adj_volume adj_factor
```

* The index is the trading date, timezone-aware in `Asia/Kolkata`.
* `adjust="split"` (default) handles splits, consolidations, bonuses and rights;
  `adjust="total"` also handles dividends (use it for returns); `adjust=None` gives raw prices.
* Old tickers work: `bp.history("ZOMATO", ...)` returns ZOMATO rows before 9 Apr 2025
  and ETERNAL rows after, in one frame.
* The first long request downloads the whole market for those days (one file per day) into
  the cache. Later requests for **any** stock in that range are instant and work offline.

## Indices

```python
bp.history("NIFTY 50", "2015-01-01")        # also "BANKNIFTY", "NIFTY IT", "INDIA VIX", ...
bp.constituents("NIFTY 500")                # today's members with ISIN and industry
bp.constituents("NIFTY 50", as_of="2018-06-01")
bp.indices.available()                      # indices with constituent files
```

## Whole market, survivorship-free

```python
day = bp.market("2026-10-19")                # every NSE stock on one day
panel = bp.universe("2020-01-01", "2020-12-31")   # (date, symbol) panel incl. later-delisted names
```

## Derivatives

```python
bp.fno.bhavcopy("2026-10-19")               # every future and option that day
bp.futures("NIFTY", "2026-01-01", expiry="near")   # continuous near-month series
bp.option_chain("NIFTY")                    # live snapshot (bid/ask, OI, IV)
bp.expiries("BANKNIFTY"); bp.lot_sizes()
bp.expiry_calendar("NIFTY", "2024-01-01")   # historical expiry dates
```

## Calendar, flows, deals, BSE

```python
bp.holidays(2026); bp.trading_days("2026-01-01", "2026-03-31"); bp.is_trading_day("2026-10-20")
bp.fii_dii(); bp.bulk_deals("2026-10-01"); bp.block_deals("2026-09-01")
bp.bse.history("500325", "2024-01-01")      # BSE by scrip code, ISIN or ticker
bp.bse.nse_bse_map()                        # NSE symbol <-> BSE code via ISIN
```

## Settings

```python
bp.configure(cache_dir="~/data/bhavpy", rate=2, offline=False, progress=True)
```

or environment variables `BHAVPY_CACHE_DIR`, `BHAVPY_RATE`, `BHAVPY_OFFLINE=1`.

## Keeping data fresh

```bash
bhavpy update --from 2015-01-01   # first time: backfill
bhavpy update                     # afterwards: only missing days (cron / Task Scheduler)
```

`update` also stores today's FII/DII numbers and index-constituent snapshots, so running it
daily builds history that NSE itself does not keep online.

## Async

```python
import asyncio, bhavpy.aio as bpa
frames = asyncio.run(asyncio.gather(*(bpa.history(s, "2024-01-01") for s in ["TCS", "INFY"])))
```

The global rate limit still applies across concurrent calls.

## Errors

| Exception | Meaning |
|---|---|
| `NotAvailable` | the exchange has no file for that request (holiday, not yet published, before archive start) |
| `BlockedError` | the exchange refused (HTTP 401/403/429 or a bot page). bhavpy never bypasses this; wait, or lower `rate` |
| `FormatChanged` | a file layout changed — please open an issue with the message |
| `SymbolNotFound` | no rows for that symbol/range, even through renames |

All inherit from `bp.BhavpyError`.

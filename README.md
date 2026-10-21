# bhavpy

**Indian stock market data (NSE + BSE) from the exchanges' own public archives — with
corporate-action adjusted prices you can audit, a local cache, and a parser suite that is
tested against the real servers every day.**

[![CI](https://github.com/rishitmpatel/bhavpy/actions/workflows/ci.yml/badge.svg)](https://github.com/rishitmpatel/bhavpy/actions/workflows/ci.yml)
[![Live sources](https://github.com/rishitmpatel/bhavpy/actions/workflows/live.yml/badge.svg)](https://github.com/rishitmpatel/bhavpy/actions/workflows/live.yml)
[![PyPI](https://img.shields.io/pypi/v/bhavpy.svg)](https://pypi.org/project/bhavpy/)
[![Python](https://img.shields.io/pypi/pyversions/bhavpy.svg)](https://pypi.org/project/bhavpy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

*Bhav* (भाव) means "price"; the *bhavcopy* is the end-of-day file NSE and BSE publish
for every trading day since 1994. bhavpy turns those files into clean pandas DataFrames.

## 30-second quickstart

```bash
pip install bhavpy
```

```python
import bhavpy as bp

df = bp.history("RELIANCE", "2015-01-01")   # raw + adjusted OHLCV, IST dates
df[["close", "adj_close", "adj_factor"]].tail()

bp.factors("RELIANCE", "2015-01-01")         # every split/bonus/rights event, its factor and source
bp.history("NIFTY 50", "2020-01-01")         # index history (also "BANKNIFTY", "INDIA VIX", ...)
bp.constituents("NIFTY 50", as_of="2019-06-01")   # point-in-time members (no survivorship bias)
bp.option_chain("NIFTY")                     # live option-chain snapshot
```

```bash
bhavpy download RELIANCE --from 2015-01-01 --adjusted -o reliance.csv
bhavpy update                                 # fetch only the days you don't have yet
```

The first request for a long range downloads one archive file per trading day for the
**whole market** (about 2,900 files for 2015 → today, ~15–35 minutes at the polite
default of 3 requests/s, ~45 MB of cache per year). After that every stock, including
delisted ones, is instant and works offline.

## Why bhavpy

| | jugaad-data | nselib | nsepython | yfinance | **bhavpy** |
|---|:-:|:-:|:-:|:-:|:-:|
| Official exchange archives (not fragile live JSON) | partial | – | – | – (Yahoo) | **✓** |
| Split / bonus / rights adjusted prices | – | – | – | ✓ (opaque) | **✓ price-checked** |
| Dividend-adjusted (total return) | – | – | – | ✓ | **✓** |
| Per-event adjustment audit table | – | – | – | – | **✓** |
| Old tickers resolve (`ZOMATO` → `ETERNAL`) | – | – | – | – | **✓** |
| Delisted stocks / survivorship-free universe | – | – | – | – | **✓** |
| Point-in-time index constituents | – | – | – | – | **✓ NIFTY 50 since 2016** |
| Local cache, offline, incremental updates | partial | – | – | – | **✓** |
| Holidays + Muhurat/Budget/DR special sessions | static list | ✓ | ✓ | – | **✓ 2005+** |
| F&O bhavcopy, futures, option chain, lots, expiries | partial | ✓ | ✓ | – | **✓** |
| BSE + NSE↔BSE ISIN map | – | – | – | `.BO` | **✓** |
| Daily test against real servers, auto-issue on breakage | – | – | – | – | **✓** |
| Typed (mypy strict), CI on Linux/macOS/Windows | – | – | – | partial | **✓** |
| Licence | – | Apache-2.0 | GPL-3.0 | Apache-2.0 | **MIT** |

Details, sources and issue links: [docs/research.md](docs/research.md).

## Adjusted prices you can check

Free sources often get Indian corporate actions wrong (bonuses, rights, demergers) and
don't tell you what they did. bhavpy:

1. takes ratios from **NSE's corporate-actions feed** (split FV 10→2, bonus 1:1, rights 1:15 @ ₹1,257 …),
2. converts them to factors (split `new/old`, bonus `b/(a+b)`, rights via theoretical ex-rights price, dividends `(P−D)/P` in `adjust="total"`),
3. **checks each split/bonus against the actual overnight price move** and refuses to apply records the market contradicts,
4. flags split-like price gaps that have no record (`unexplained_gap`),
5. returns raw *and* adjusted columns plus `df.attrs["events"]`.

```python
>>> bp.history("RELIANCE", "2024-10-24", "2024-10-29")[["close", "adj_close", "adj_factor"]]
                            close  adj_close  adj_factor
date
2024-10-24 00:00:00+05:30  2679.60   1339.800         0.5
2024-10-25 00:00:00+05:30  2655.70   1327.850         0.5
2024-10-28 00:00:00+05:30  1334.35   1334.350         1.0     # 1:1 bonus ex-date
2024-10-29 00:00:00+05:30  1340.00   1340.000         1.0
>>> bp.factors("RELIANCE", "2024-10-01", "2024-11-01")[["ex_date", "kind", "ratio", "price_factor", "check", "source"]]
                    ex_date   kind ratio  price_factor check                 source
0 2024-10-28 00:00:00+05:30  bonus   1:1           0.5    ok  nse_corporate_actions
```

Adjusted values are expressed in the share terms of the **last row returned**.

## What's included

| Area | Functions |
|---|---|
| Equity history | `history`, `factors`, `corporate_actions`, `market` (one day, all stocks), `universe` (panel incl. delisted) |
| Indices | `history("NIFTY 50")` / `index_history`, `constituents(index, as_of=)`, `indices.available()` |
| Symbols | `equity_list` (ISIN, listing date, face value), `resolve`, `symbol_chain`, `symbols.symbol_changes / name_changes / delisted / info` |
| F&O | `fno.bhavcopy`, `futures` (near/next/far continuous), `fno.options`, `option_chain` (live), `expiries`, `expiry_calendar`, `lot_sizes` |
| Calendar | `holidays`, `trading_days`, `is_trading_day`, `next_trading_day`, `previous_trading_day`, `calendar.special_sessions` |
| Flows & deals | `fii_dii`, `fii_dii_history`, `bulk_deals`, `block_deals` |
| BSE | `bse.bhavcopy`, `bse.history` (scrip code / ISIN / ticker), `bse.nse_bse_map` |
| Plumbing | `update`, `configure`, `bhavpy.aio` (async wrappers), CLI `bhavpy …` |

All DataFrames use snake_case columns and an `Asia/Kolkata` tz-aware `date` index.

## Reliability

* **Archives first.** Daily bhavcopy/index/symbol files have had stable URLs for years
  (one format change, July 2024, handled). Live JSON is used only for things that have no
  archive: option chain, corporate actions, holidays, FII/DII, deal history.
* **Polite by default.** ≤3 requests/s per host, retries with exponential backoff, honest
  `bhavpy/<version>` User-Agent suffix, local cache so nothing is downloaded twice.
* **Clear errors.** `NotAvailable` (holiday / not yet published), `BlockedError` (the
  exchange refused; bhavpy never bypasses blocks or CAPTCHAs), `FormatChanged` (a file
  layout changed — please open an issue), `SymbolNotFound`.
* **One file per source.** When NSE changes a URL or column, the fix is one module in
  [`src/bhavpy/sources/`](src/bhavpy/sources).
* **Daily live tests.** [`tests/live`](tests/live) runs against the real servers every
  day on GitHub Actions and opens an issue automatically when something breaks.

See [Reliability](https://rishitmpatel.github.io/bhavpy/reliability/) for what is solid
vs. fragile and why.

## Documentation

<https://rishitmpatel.github.io/bhavpy/> — quickstart, API, and a cookbook:
NIFTY 50 history, adjusted returns, a moving-average backtest, option chain → IV smile.
A notebook is in [`examples/quickstart.ipynb`](examples/quickstart.ipynb).

## Disclaimer

bhavpy is an independent open-source project. **It is not affiliated with, endorsed by,
or connected to the National Stock Exchange of India (NSE), BSE Ltd, or NSE Indices Ltd.**
"NSE", "BSE", "NIFTY" and related names are trademarks of their owners.

Data is fetched from public exchange websites **for personal and research use**. The
exchanges' terms of use restrict automated data collection and redistribution; **you are
responsible for complying with them** (see [docs/research.md](docs/research.md#3-terms-of-use)).
For commercial use or redistribution, license data from the exchanges or an authorised
vendor. Data may contain errors or omissions; verify anything important.
**Nothing in this project is investment advice.**

## Contributing

Bug reports with the exact error text are gold — see [CONTRIBUTING.md](CONTRIBUTING.md).
Issues labelled [good first issue](https://github.com/rishitmpatel/bhavpy/labels/good%20first%20issue)
are a good place to start.

MIT licensed.

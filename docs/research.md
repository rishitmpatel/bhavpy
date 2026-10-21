# Research notes (checked live on 2026-10-21)

Everything below was checked against the live sites and package indexes on
**2026-10-21**, not from memory. Re-run `pytest -m live tests/live` to re-verify the
data-source claims; the scheduled CI job does this every day.

## 1. Existing libraries

| Library | Latest release | Stars / open issues | Data path | What breaks / what's missing |
|---|---|---|---|---|
| [jugaad-data](https://github.com/jugaad-py/jugaad-data) | 0.35.10 (2026-10-06) | 587 / 27 | NSE live JSON APIs + some archives | F&O bhavcopy download broken ([#121](https://github.com/jugaad-py/jugaad-data/issues/121), [#136](https://github.com/jugaad-py/jugaad-data/issues/136)); silently returns the previous day's bhavcopy on holidays ([#131](https://github.com/jugaad-py/jugaad-data/issues/131)); split handling open since 2023 ([#69](https://github.com/jugaad-py/jugaad-data/issues/69)); index history problems ([#48](https://github.com/jugaad-py/jugaad-data/issues/48), [#71](https://github.com/jugaad-py/jugaad-data/issues/71)); hard-coded holiday list ([#70](https://github.com/jugaad-py/jugaad-data/issues/70)). `stock_df` relies on `nseindia.com/api/historical/...`, which today answers scripted clients with a bot-check page. |
| [nselib](https://github.com/RuchiTanmay/nselib) | 2.5.1 (2026-05-01) | 181 / 7 | NSE live JSON APIs | No ISIN in `equity_list` ([#127](https://github.com/RuchiTanmay/nselib/issues/127)); SME bhavcopy filename bug ([#126](https://github.com/RuchiTanmay/nselib/issues/126)); broken import ([#104](https://github.com/RuchiTanmay/nselib/issues/104)); `index_data` capped at 70 rows ([#99](https://github.com/RuchiTanmay/nselib/issues/99)); constituents error ([#98](https://github.com/RuchiTanmay/nselib/issues/98)); race condition on a shared temp CSV ([#96](https://github.com/RuchiTanmay/nselib/issues/96)); option chain broke twice ([#85](https://github.com/RuchiTanmay/nselib/issues/85), [#93](https://github.com/RuchiTanmay/nselib/issues/93)); no adjustment ([#77](https://github.com/RuchiTanmay/nselib/issues/77)). |
| [nsepython](https://github.com/aeron7/nsepython) | 2.101 (2026-10-07) | 371 / 5 (GPL-3.0) | NSE live JSON APIs | `equity_history` KeyError after endpoint 404 ([#74](https://github.com/aeron7/nsepython/issues/74)); several functions broken ([#75](https://github.com/aeron7/nsepython/issues/75), [#77](https://github.com/aeron7/nsepython/issues/77)); JSON decode errors when NSE changes ([#57](https://github.com/aeron7/nsepython/issues/57), [#78](https://github.com/aeron7/nsepython/issues/78)); historical URL changes ([#63](https://github.com/aeron7/nsepython/issues/63)); `os.popen` command-injection report ([#73](https://github.com/aeron7/nsepython/issues/73)). GPL licence limits reuse. |
| [nsepy](https://github.com/swapniljariwala/nsepy) | 0.8 (2020-03-07) | 807 / 164 | old www1.nseindia.com pages | **Dead**: the old NSE site it scraped was retired. |
| [yfinance](https://github.com/ranaroussi/yfinance) `.NS` / `.BO` | 1.7.0 (2026-08-26) | 25.6k / 108 | Yahoo Finance | Not exchange data. Reports of wrong/missing NSE data ([#2055](https://github.com/ranaroussi/yfinance/issues/2055), [#2022](https://github.com/ranaroussi/yfinance/issues/2022), [#2612](https://github.com/ranaroussi/yfinance/issues/2612)), splits not applied ([#1531](https://github.com/ranaroussi/yfinance/issues/1531)), dividend-date errors ([#2377](https://github.com/ranaroussi/yfinance/issues/2377)); users report wrong Indian dividends and demergers ([Quantra thread](https://quantra.quantinsti.com/community/t/corporate-actions/26346), [TradingQnA thread](https://tradingqna.com/t/has-anyone-found-wrong-adjusted-prices-in-nse-historical-data-for-backtesting/192938)). No delisted names, no F&O, no constituents, no bhavcopy turnover/trades, adjustment not auditable. |
| [nsetools](https://github.com/vsjha18/nsetools) | 2.0.1 (2025-03-18) | 908 / 2 | NSE live quotes | Live quotes only, no history. |
| [bsedata](https://github.com/sdabhi23/bsedata) | 0.6.0 (2024-03-14) | 116 / 4 | BSE live quotes | Live quotes only. |
| [openchart](https://github.com/marketcalls/openchart) | 0.2.0 (2026-01-16) | 83 / 10 | NSE charting API | Intraday/EOD candles; no adjustment, no corporate actions, no cache. |
| [nsefin](https://pypi.org/project/nsefin/) | 0.1.5 (2025-09-08) | – | NSE live JSON | Young, small surface. |

**Common pattern:** most libraries wrap NSE's *live website JSON*, which changes often and
is bot-protected, and none publishes a test that runs against the real site. That is why
"X stopped working" is the most common issue type above.

## 2. Data sources (all public, no login)

Archive files (stable, bulk) are preferred. Live JSON is used only where no archive exists.

| Data | URL pattern | Coverage verified | Notes |
|---|---|---|---|
| NSE equity bhavcopy (UDiFF) | `nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip` | 2024-07-08 → today | New format since 8 Jul 2024. |
| NSE equity bhavcopy (legacy) | `nsearchives.nseindia.com/content/historical/EQUITIES/YYYY/MON/cmDDMONYYYYbhav.csv.zip` | 1994-11-03 → 2024-07-05 | ISIN column from ~2011; `TOTALTRADES` from ~2010. `HEAD` always answers 200 here; only `GET` tells the truth. |
| NSE F&O bhavcopy | `.../content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip`, legacy `.../historical/DERIVATIVES/YYYY/MON/foDDMONYYYYbhav.csv.zip` | 2023 legacy and 2026 UDiFF checked | UDiFF adds lot size and underlying price. |
| NSE index closes | `.../content/indices/ind_close_all_DDMMYYYY.csv` | 2012-03-01 → today | Index names changed over time (`S&P CNX Nifty` → `CNX Nifty` → `Nifty 50`). Older index history is not in this archive. |
| Delivery data | `.../products/content/sec_bhavdata_full_DDMMYYYY.csv` | 2020-01-02 → today | Not in v1 (roadmap). |
| Security master | `.../content/equities/EQUITY_L.csv`, `.../emerge/corporates/content/SME_EQUITY_L.csv` | current | Includes ISIN, listing date, face value. |
| Symbol / name changes, delistings | `.../content/equities/symbolchange.csv`, `namechange.csv`, `delisted.csv` | full history | ~1,070 symbol changes, ~2,330 name changes. |
| F&O lot sizes | `.../content/fo/fo_mktlots.csv` | current | Two header blocks (index, stock). |
| Bulk / block deals (today) | `.../content/equities/bulk.csv`, `block.csv` | current day | |
| Index constituents | `www.niftyindices.com/IndexConstituent/ind_<code>list.csv` | current | 27 index files checked. Snapshot only, no history. |
| BSE equity bhavcopy | `www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV`, legacy `EQ_ISINCODE_DDMMYY.zip` | UDiFF 2024-07-08 →; legacy 2017-01 → 2024-07-05 | Missing files come back as HTTP 200 with the site's HTML shell. Pre-2017 legacy files are no longer served. |

Live JSON endpoints on `www.nseindia.com/api/...` (worked on 2026-10-21 **without cookies**
with a browser-like `User-Agent` and a `Referer: https://www.nseindia.com/` header):

| Endpoint | Used for | Status |
|---|---|---|
| `holiday-master?type=trading&year=YYYY` | trading calendar | works, years 2011–2026 |
| `corporates-corporateActions?index=equities&symbol=X&from_date=&to_date=` | splits/bonus/rights/dividends | works, history back to the 2000s |
| `option-chain-contract-info?symbol=X` | expiries, strikes | works |
| `option-chain-v3?type=Indices\|Equity&symbol=X&expiry=DD-Mon-YYYY` | option chain snapshot | works |
| `fiidiiTradeReact` | FII/DII cash flows (latest day only) | works |
| `historicalOR/bulk-block-short-deals?optionType=bulk_deals\|block_deals&from=&to=` | deal history | works |
| `option-chain-indices`, `equity-stockIndices` | (used by older libraries) | **404, retired** |
| `historical/cm/equity` | (used by jugaad-data / nsepython) | **bot-check HTML page** for scripted clients; bhavpy does not use it |

Headers: the archive host drops connections from a bare non-browser `User-Agent`; a
browser `User-Agent` with an honest `bhavpy/<version>` suffix works. The `www.nseindia.com`
home page answers 403 to scripted clients; bhavpy never needs it, and does not try to get
around it. `api.bseindia.com` also answers 403; bhavpy uses only BSE's download files.

Other checked sources: the `niftyindices.com` historical-data POST endpoint returned an
error, and the NSE "PR" zip (`archives/equities/bhavcopy/pr/PRDDMMYY.zip`) is not served
for 2008. Neither is needed.

### An important finding for adjustment

The bhavcopy `PREVCLOSE` / `PrvsClsgPric` field is **not** rebased on split/bonus
ex-dates. On RELIANCE's 1:1 bonus (ex-date 2017-09-07) the file shows close 818.10 and
prev close 1645.40; on the 2024-10-28 bonus it shows 1334.35 and 2655.70. So
adjustment cannot be derived from the bhavcopy alone; bhavpy uses NSE's
corporate-actions feed for the ratios and checks each one against the actual overnight
price move. Dividends are also not reflected in prev close (RELIANCE ex-dividend
2026-06-05: prev close 1303.70 = previous day's close).

## 3. Terms of use

* **NSE** ([nseindia.com terms](https://www.nseindia.com/static/nse-terms-of-use), read 2026-10-21):
  *"User is prohibited to conduct any systematic or automated data collection activities
  (including scraping, data mining, data extraction and data harvesting) on or in relation
  to our Website / Mobile Application."* It also says content shall not be *"copied,
  modified ... reproduced, ... distributed ... sold"*. NSE's
  [robots.txt](https://www.nseindia.com/robots.txt) allows `/` and disallows only `/market-data-test`.
* **NSE Indices** ([niftyindices.com terms](https://www.niftyindices.com/terms-of-use)):
  *"You may not conduct any systematic or automated data collection activities ... without
  our express written consent"* and the site *"may be used only ... for personal,
  non-commercial use only."*
* **BSE**: the terms pages are JavaScript-only and could not be read by an automated
  fetch. BSE's published disclaimers say material may not be reproduced or redistributed
  without prior written permission ([example](https://bseindia.com/static/fpi/Disclaimer.aspx)).
  Treat BSE data with the same restrictions as NSE's.

**What this means for bhavpy and its users.** The exchanges' terms restrict automated
collection and redistribution. bhavpy is a tool that an individual runs on their own
machine; it does not host or redistribute data. It keeps load low (archive files, local
cache, 3 requests/s cap, incremental updates), identifies itself in the User-Agent, never
bypasses blocks, cookies walls or CAPTCHAs, and stops with a clear error when refused.
**Users are responsible for complying with the exchanges' terms**, including getting
permission where required. For commercial use or redistribution, license data from NSE
(NSE Data & Analytics) or BSE, or an authorised vendor.

## 4. Gap table: what bhavpy does better

| Need | jugaad-data | nselib | nsepython | yfinance | **bhavpy** |
|---|---|---|---|---|---|
| Data from official archives (not fragile live JSON) | partial | ✗ | ✗ | ✗ (Yahoo) | **✓ archives first, live JSON only for option chain, corp actions, flows, holidays** |
| Split/bonus/rights adjusted prices | ✗ | ✗ | ✗ | ✓ (opaque, errors reported) | **✓ exchange ratios, price-checked, factor table per event** |
| Dividend (total-return) adjustment | ✗ | ✗ | ✗ | ✓ | **✓ `adjust="total"`** |
| Audit trail of adjustments | ✗ | ✗ | ✗ | ✗ | **✓ `bp.factors()`: source, factor, check** |
| Old tickers resolve (renames) | ✗ | ✗ | ✗ | ✗ | **✓ `ZOMATO` → `ETERNAL`, stitched history** |
| Delisted stocks / survivorship-free universe | ✗ | ✗ | ✗ | ✗ | **✓ every stock in every bhavcopy, `bp.universe()`** |
| Point-in-time index constituents | ✗ | current only | current only | ✗ | **✓ NIFTY 50 since 2016 (validated), snapshots for others** |
| Local cache + offline + incremental update | partial | ✗ | ✗ | ✗ | **✓ SQLite, `bhavpy update`** |
| Holidays & special sessions | hard-coded list | via pandas_market_calendars | ✓ live | ✗ | **✓ API 2011+, archive-derived 2005+, Muhurat/Budget/DR sessions** |
| F&O bhavcopy, futures series, option chain, lots, expiries | partial | ✓ | ✓ | ✗ | **✓** |
| BSE + NSE↔BSE ISIN map | ✗ | ✗ | ✗ | `.BO` only | **✓** |
| Daily live test against real servers, auto-issue on breakage | ✗ | ✗ | ✗ | ✗ | **✓ GitHub Actions schedule** |
| One module per source | ✗ | ✗ | single file | n/a | **✓ `bhavpy/sources/*`** |
| Typed (mypy strict), CI on 3 OSes × 4 Pythons | ✗ | ✗ | ✗ | partial | **✓** |
| Licence | none detected by GitHub | Apache-2.0 | GPL-3.0 | Apache-2.0 | **MIT** |

## 5. Name

Candidates (all free on PyPI on 2026-10-21; none taken under `rishitmpatel` on GitHub):

1. **`bhavpy`** — *bhav* means "price" in Hindi/Gujarati/Marathi and is the root of
   *bhavcopy*, the exchange file the library is built on. Short, pronounceable, says what
   it does to anyone in Indian markets, no exchange trademark in it.
2. `dalalpy` — after Dalal Street. Catchy, but evokes BSE specifically and "dalal" also
   means "broker/middleman".
3. `tejimandi` — "bull/bear market" in Hindi. Fun, but long, and a well-known Indian
   advisory app already uses the name *Teji Mandi*.

**Pick: `bhavpy`.** (PyPI names `bhav` and `bhavcopy` are taken by unrelated small
projects; `bhavpy` is distinct.)

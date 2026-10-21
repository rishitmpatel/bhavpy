# Adjusted prices

Getting Indian corporate actions right is the main reason bhavpy exists.

## What gets adjusted

Each corporate action becomes a **price factor** multiplied into every price *before*
its ex-date. Factors of later events multiply, so the newest prices are never changed
and older prices are expressed in today's share terms (relative to the last row returned).

| Action (NSE wording) | Factor | Example |
|---|---|---|
| Face value split, `From Rs 10 To Rs 2` | new FV / old FV | 0.2 |
| Consolidation, `From Rs 1 To Rs 10` | new FV / old FV | 10 |
| `Bonus a:b` (a new for every b held) | b / (a + b) | 1:1 → 0.5, 1:2 → 0.667 |
| `Rights a:b @ Premium Rs P` | TERP / P<sub>cum</sub>, TERP = (b·P<sub>cum</sub> + a·S)/(a+b), S = P + face value | RELIANCE 2020: 0.9906 |
| Dividend `Rs D` (only `adjust="total"`) | (P<sub>cum</sub> − D) / P<sub>cum</sub> | CRSP-style total return |
| Demerger / scheme of arrangement | estimated: ex-day price-discovery open / P<sub>cum</sub> (close if the open was stale); `check="estimated"`. `demerger="ignore"` leaves it unadjusted | RELIANCE 2023 (Jio Financial): 0.908 |

P<sub>cum</sub> is the last close before the ex-date. Volumes are scaled by the inverse
factor for splits, consolidations and bonuses.

## Where the ratios come from

NSE's corporate-actions feed (the same data as the *Corporate Actions* page on
nseindia.com), cached locally. The free-text subjects (`"Fv Splt Frm Rs 10 To Rs 2"`,
`"Int Div-Rs.2.50/- Per Share Purpose Revised"`, ...) are parsed by
`bhavpy.sources.nse_corpactions.parse_subject`, tested on the spellings found in
~9,000 real records from 2010–2026.

Note: the bhavcopy's own `prev_close` is **not** rebased on ex-dates, so it cannot be used
to infer adjustments (see [research](research.md#an-important-finding-for-adjustment)).

## Checks

* **Price check.** For splits, bonuses and consolidations bhavpy compares the expected
  factor (all such events on one ex-date multiplied together) with the actual overnight move `open(ex-date) / close(day before)`. If they differ
  by more than 25%, the record is marked `check="mismatch"`, **not applied**, and a warning
  is raised. Pass `on_mismatch="apply"` to apply it anyway.
* **Gap scan.** Overnight moves beyond −23%/+30% that match a common split/bonus
  ratio within 6% but have no record are reported as `kind="unexplained_gap"`. They are
  applied only with `infer=True` — or automatically if the corporate-actions feed could not
  be reached, so adjustment still works when NSE's site is down.

## Inspect everything

```python
f = bp.factors("RELIANCE", "2005-01-01", adjust="total")
f[["ex_date", "kind", "ratio", "amount", "price_factor", "cumulative_factor", "check", "source"]]
```

The same table is attached to every adjusted frame as `df.attrs["events"]`.

## Validated examples (in the unit tests)

| Stock | Ex-date | Action | Raw move | Adjusted move |
|---|---|---|---|---|
| RELIANCE | 2017-09-07 | bonus 1:1 (legacy file format) | −50.3% | −0.6% |
| RELIANCE | 2024-10-28 | bonus 1:1 (UDiFF format) | −49.8% | +0.5% |
| SHRIRAMFIN | 2025-01-10 | split FV 10 → 2 | −81.1% | −5.3% |
| RELIANCE | 2020-05-13 | rights 1:15 @ ₹1,257 | | factor 0.9906 (TERP) |
| RELIANCE | 2026-06-05 | dividend ₹6 (`total`) | | factor (P−6)/P |
| BAJFINANCE | 2025-06-16 | bonus 4:1 **and** split FV 2 → 1 on one day | ≈ −90% | continuous (combined factor 0.1) |
| RELIANCE | 2023-07-20 | Jio Financial demerger | −9.2% | factor 2,580 / 2,841.85 (price discovery) |

**Whole-index checks** (`python scripts/validate_adjustment.py "NIFTY 500"`, run on the
full 2015–2026 cache on 2026-10-21): across the 499 NIFTY 500 members with data, 340
corporate actions were applied to 211 stocks with **zero price-check mismatches**; one
overnight jump was flagged as an unexplained gap (FORCEMOT 2024-02-14, a genuine +33%
results-day move — reported, not applied). The largest adjusted daily moves are all real
market events (YESBANK 2020-03-06, RPOWER 2019-02-04, POLICYBZR 2026-09-24, ...).

For the NIFTY 50 alone: for all 50 NIFTY 50 members,
the largest adjusted daily move is the March 2020 COVID crash or a known event-day move
(e.g. AXISBANK −28% on 2020-03-23) — no split, bonus or rights date shows up as a jump. The
only ex-dates that needed the demerger estimate were ADANIENT 2015-06-03, TMPV (Tata Motors)
2025-10-14, RELIANCE 2023-07-20, ITC 2025-01-06 and HINDUNILVR 2025-12-05.

The live suite repeats the RELIANCE 2024 check against the real servers every day.

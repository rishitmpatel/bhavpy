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
| Demerger / capital reduction | not adjusted by default (`demerger="estimate"` uses ex-day open / cum close) | |

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
  factor with the actual overnight move `open(ex-date) / close(day before)`. If they differ
  by more than 25%, the record is marked `check="mismatch"`, **not applied**, and a warning
  is raised. Pass `on_mismatch="apply"` to apply it anyway.
* **Gap scan.** Overnight moves of more than −33%/+50% that match a common split/bonus
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

The live suite repeats the RELIANCE 2024 check against the real servers every day.

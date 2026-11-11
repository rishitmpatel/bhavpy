# Survivorship-free momentum backtest

Cross-sectional 12-1 momentum on the NIFTY 50, rebalanced monthly: at each
month-end, hold the 10 index members with the strongest prior-year momentum
equal-weighted for the next month.

The survivorship work is done by two functions together.
`bp.constituents("NIFTY 50", as_of=...)` returns the membership **as it was**
on each rebalance date, and `bp.universe(...)` returns prices for every stock
that traded in the window — including names that later left the index or were
delisted. Testing today's constituent list against old prices instead would
silently drop every loser that ever left the index, and flatter the result.

```python
import bhavpy as bp
import numpy as np
import pandas as pd

START, END = "2018-01-01", "2023-12-31"

# Prices for everything that traded (delisted names included), with a year
# of lookback before START for the 12-1 signal.
panel = bp.universe("2017-01-01", END)
close = panel["close"].unstack("symbol").sort_index()

monthly = close.resample("ME").last()
ret_m = monthly.pct_change()
signal = monthly.shift(1) / monthly.shift(12) - 1  # 12-1 momentum, known at month-end

weights = pd.DataFrame(0.0, index=monthly.index, columns=monthly.columns)
for date, sig in signal.iterrows():
    members = bp.constituents("NIFTY 50", as_of=date)["symbol"]
    ranked = sig[[s for s in members if s in sig.index]].dropna()
    if len(ranked) >= 10:
        weights.loc[date, ranked.nlargest(10).index] = 0.1

gross = (weights.shift(1) * ret_m).sum(axis=1)             # weights set at t earn month t+1
cost = 0.001 * weights.diff().abs().sum(axis=1).shift(1)   # 10 bps on turnover
port = (gross - cost).loc[START:END].fillna(0)

def stats(r):
    curve = (1 + r).cumprod()
    years = len(r) / 12
    cagr = curve.iloc[-1] ** (1 / years) - 1
    sharpe = r.mean() / r.std() * np.sqrt(12)
    dd = (curve / curve.cummax() - 1).min()
    return f"CAGR {cagr:6.1%}  Sharpe {sharpe:4.2f}  MaxDD {dd:6.1%}"

print("top-10 momentum:", stats(port))
```

Two timing details keep the test honest: the signal at a month-end is built
from prices up to the *previous* month-end (the skipped month is what makes
it "12-1" rather than "12-0"), and the weights chosen at a month-end only
start earning the following month's return.

One caveat: `universe()` returns raw bhavcopy closes, so a split or bonus
inside a stock's formation window distorts its signal until it rolls out of
the lookback. The point of this recipe is the membership handling; adjusting
the panel (see [Adjusted returns](adjusted-returns.md)) is left as an
exercise.

!!! note
    This is a teaching example, not a trading system and not investment advice.

# Simple moving-average backtest

A long-only 50/200-day crossover on adjusted prices. It trades on the **next** day's
close after a signal, to avoid look-ahead bias.

```python
import bhavpy as bp
import numpy as np

px = bp.history("TCS", "2015-01-01", adjust="total")["adj_close"]

fast, slow = px.rolling(50).mean(), px.rolling(200).mean()
signal = (fast > slow).astype(int)
position = signal.shift(1).fillna(0)            # act the day after the signal

ret = px.pct_change().fillna(0)
cost = 0.001 * position.diff().abs().fillna(0)  # 10 bps per change in position
strat = position * ret - cost

def stats(r):
    curve = (1 + r).cumprod()
    years = len(r) / 252
    cagr = curve.iloc[-1] ** (1 / years) - 1
    sharpe = r.mean() / r.std() * np.sqrt(252)
    dd = (curve / curve.cummax() - 1).min()
    return f"CAGR {cagr:6.1%}  Sharpe {sharpe:4.2f}  MaxDD {dd:6.1%}"

print("buy & hold:", stats(ret))
print("SMA 50/200:", stats(strat))
```

Why adjusted prices matter here: on a raw series every bonus or split looks like a crash,
which flips the moving averages and creates fake trades. With `adjust="total"` the
series is continuous and dividends are counted in the return.

!!! note
    This is a teaching example, not a trading system and not investment advice.

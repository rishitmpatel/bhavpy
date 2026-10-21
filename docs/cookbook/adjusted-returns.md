# Build adjusted returns

Use `adjust="total"` for return calculations: it adjusts for dividends as well as splits,
bonuses and rights, so `adj_close.pct_change()` is a total-return series.

```python
import bhavpy as bp
import numpy as np
import pandas as pd

df = bp.history("RELIANCE", "2015-01-01", adjust="total")

raw = df["close"].pct_change()
adj = df["adj_close"].pct_change()
print(raw.min(), adj.min())       # raw has -50% "crashes" on bonus ex-dates; adjusted does not

cagr = (df["adj_close"].iloc[-1] / df["adj_close"].iloc[0]) ** (252 / len(df)) - 1
vol = np.log(df["adj_close"]).diff().std() * np.sqrt(252)
print(f"CAGR {cagr:.1%}, annualised vol {vol:.1%}")
```

## See exactly what was adjusted

```python
bp.factors("RELIANCE", "2015-01-01", adjust="total")[
    ["ex_date", "kind", "ratio", "amount", "price_factor", "cumulative_factor", "check"]
]
```

## Returns for many stocks at once

```python
syms = ["TCS", "INFY", "HDFCBANK", "ICICIBANK", "ETERNAL"]
rets = pd.DataFrame({s: bp.history(s, "2020-01-01", adjust="total")["adj_close"] for s in syms}).pct_change()
rets.corr().round(2)
```

The first call downloads the whole market for the range once; the other symbols come from
the cache. `ETERNAL` automatically includes its history as `ZOMATO`.

## Split-only vs total

| | `adjust="split"` | `adjust="total"` |
|---|---|---|
| Splits, consolidations, bonuses, rights | ✓ | ✓ |
| Dividends | – | ✓ |
| Use for | charts, price levels, technical indicators | returns, performance, factor research |

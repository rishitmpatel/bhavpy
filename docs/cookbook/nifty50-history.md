# Download NIFTY 50 history

```python
import bhavpy as bp
import pandas as pd

nifty = bp.history("NIFTY 50", "2013-01-01")
nifty[["open", "high", "low", "close", "pe", "pb", "div_yield"]].tail()
```

The index archive starts in March 2012; old names (`S&P CNX Nifty`, `CNX Nifty`) are
mapped to `NIFTY 50` so the series is continuous.

## Plot close and valuation

```python
import matplotlib.pyplot as plt

fig, (a, b) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))
nifty["close"].plot(ax=a, title="NIFTY 50")
nifty["pe"].plot(ax=b, title="P/E")
plt.tight_layout()
```

## All 50 members' prices, point-in-time

```python
members = bp.constituents("NIFTY 50", as_of="2020-01-01")["symbol"]
closes = {s: bp.history(s, "2020-01-01", "2020-12-31")["adj_close"] for s in members}
panel = pd.DataFrame(closes)          # 2020 prices of the members *as of Jan 2020*
```

Using the as-of list (rather than today's members) avoids survivorship bias: YESBANK,
for example, was a member in January 2020 and is included.

## Save to disk

```bash
bhavpy download "NIFTY 50" --from 2013-01-01 -o nifty50.csv
```

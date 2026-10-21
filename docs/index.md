# bhavpy

Indian stock market data (NSE + BSE) from the exchanges' own public archives, as clean
pandas DataFrames — with **corporate-action adjusted prices you can audit**, a local
cache that makes repeat requests instant and offline, and a parser suite tested against
the real servers every day.

```bash
pip install bhavpy
```

```python
import bhavpy as bp

df = bp.history("RELIANCE", "2015-01-01")       # raw + adjusted OHLCV (IST dates)
bp.factors("RELIANCE", "2015-01-01")             # what was adjusted, by how much, and why
bp.constituents("NIFTY 50", as_of="2019-06-01")  # point-in-time index members
```

* [Quickstart](quickstart.md) — the main calls in five minutes.
* [Adjusted prices](adjustment.md) — how the headline feature works and how to check it.
* [Cookbook](cookbook/nifty50-history.md) — NIFTY 50 history, adjusted returns, a
  moving-average backtest, an implied-volatility smile.
* [Reliability](reliability.md) — what is solid, what is fragile, and why.
* [Research & sources](research.md) — every URL used, coverage, terms of use, and how
  bhavpy compares with other libraries.

!!! warning "Disclaimer"
    Not affiliated with NSE or BSE. Data is for personal/research use and you are
    responsible for following the exchanges' terms of use. Not investment advice.
    See the [full disclaimer](disclaimer.md).

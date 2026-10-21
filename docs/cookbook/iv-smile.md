# Option chain → implied-volatility smile

`bp.option_chain()` returns a live snapshot in long format (one row per strike and
CE/PE), including NSE's own implied volatility. You can also compute IV yourself from the
mid price with Black-Scholes.

```python
import bhavpy as bp
import matplotlib.pyplot as plt

chain = bp.option_chain("NIFTY")                  # nearest expiry
spot = chain.attrs["underlying_price"]
print(chain.attrs["timestamp"], spot)

# Out-of-the-money options carry the smile: puts below spot, calls above.
otm = chain[((chain.option_type == "PE") & (chain.strike < spot)) |
            ((chain.option_type == "CE") & (chain.strike >= spot))]
otm = otm[otm.iv > 0]

plt.plot(otm.strike, otm.iv, "o-")
plt.axvline(spot, ls="--", c="grey")
plt.xlabel("strike"); plt.ylabel("IV (%)"); plt.title("NIFTY IV smile (NSE IV)")
```

## Compute IV yourself

```python
import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm
import pandas as pd

def bs_price(S, K, T, r, sigma, kind):
    d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if kind == "CE":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def implied_vol(price, S, K, T, r, kind):
    try:
        return brentq(lambda s: bs_price(S, K, T, r, s, kind) - price, 1e-4, 5.0)
    except ValueError:
        return np.nan

expiry = chain["expiry"].iloc[0]
now = pd.Timestamp.now(tz="Asia/Kolkata")
T = max((expiry + pd.Timedelta(hours=15, minutes=30) - now).total_seconds(), 3600) / (365 * 24 * 3600)
r = 0.065                                          # approx. risk-free rate

otm = otm.assign(mid=(otm.bid + otm.ask) / 2)
otm["my_iv"] = [implied_vol(m, spot, k, T, r, t) * 100 for m, k, t in zip(otm.mid, otm.strike, otm.option_type)]
otm[["strike", "option_type", "mid", "iv", "my_iv"]]
```

!!! info
    The option chain is the one dataset bhavpy reads from NSE's live website (there is no
    archive for it). Outside market hours you get the last snapshot. For end-of-day
    history of options use `bp.fno.options("NIFTY", "2026-10-19")` from the F&O bhavcopy.

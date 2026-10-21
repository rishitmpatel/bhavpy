# Command line

```text
bhavpy download SYMBOL [--from DATE] [--to DATE] [--adjusted [split|total]] [--only-adjusted] [-o FILE]
bhavpy factors SYMBOL [--from DATE] [--total] [-o FILE]
bhavpy update [--from DATE] [--indices-only]
bhavpy constituents [INDEX] [--as-of DATE] [-o FILE]
bhavpy chain [SYMBOL] [--expiry DATE] [-o FILE]
bhavpy market [--date DATE] [--exchange nse|bse] [-o FILE]
bhavpy holidays [YEAR]
bhavpy symbol SYMBOL
bhavpy flows [--history] [-o FILE]
bhavpy deals bulk|block [--from DATE] [--to DATE] [-o FILE]
bhavpy cache info|path|vacuum|clear [--dataset NAME]
```

Global options: `--cache-dir`, `--rate`, `--offline`, `-q/--quiet`, `-v/--verbose`.

Output format follows the file extension: `.csv` (default), `.parquet`
(needs `pip install "bhavpy[parquet]"`), `.json`, `.jsonl`, `.xlsx` (needs openpyxl).
Without `-o`, CSV goes to stdout, so you can pipe: `bhavpy download TCS | head`.

Examples:

```bash
bhavpy download RELIANCE --from 2015-01-01 --adjusted -o reliance.csv
bhavpy download "NIFTY 50" --from 2013-01-01 -o nifty.parquet
bhavpy constituents "NIFTY 50" --as-of 2018-06-01
bhavpy symbol ZOMATO           # -> ETERNAL, ISIN, rename history
```

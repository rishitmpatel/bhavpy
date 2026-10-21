# Contributing to bhavpy

Thanks for helping! bhavpy's value is that it keeps working when the exchanges change
things, so reports and fixes for broken sources are the most useful contributions.

## Reporting a broken source

Open an issue using the **"Data source broke"** template and paste:

* the exact error text (`FormatChanged: ...` messages include the URL and the columns seen),
* `bhavpy --version` and your Python version,
* the call you made.

The scheduled [live test workflow](.github/workflows/live.yml) opens an issue labelled
`source-broken` automatically when a source fails; add details there if you see one.

## Development setup

```bash
git clone https://github.com/rishitmpatel/bhavpy
cd bhavpy
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                 # unit tests: recorded files only, no network
ruff check src tests && ruff format --check src tests
mypy
pytest -m live tests/live   # optional: hits the real NSE/BSE servers
```

## How the code is organised

```
src/bhavpy/
  sources/     one module per upstream file or endpoint: URL + parser, nothing else
  http.py      the only place that talks to the network (rate limit, retries, errors)
  cache.py     SQLite cache and fetch log
  store.py     "make sure these days are cached" engine
  adjust.py    corporate-action factors and price checks
  equity.py, indices.py, fno.py, flows.py, bse.py, calendar.py, symbols.py   public API
  cli.py       command line
```

**Fixing a source** usually means editing one file in `sources/`:

1. Download the new file (or JSON) and save a *trimmed* copy (a handful of rows) in
   `tests/fixtures/`, keeping the real header and formatting.
2. Update the parser; keep the canonical output columns unchanged.
3. Add or update a test in `tests/test_parsers.py` that parses the new fixture.
4. Run `pytest -m live tests/live -k <name>` to confirm against the real server.

**Adding a source**: create `sources/<exchange>_<thing>.py` with the URL builder and a
pure `parse(raw: bytes) -> DataFrame`, a fixture, a parser test, a live test, and a
public function in the relevant module.

## Rules of the road

* Public, no-login sources only. Never add code that bypasses blocks, cookie walls,
  CAPTCHAs or rate limits, and never use paid/private APIs.
* Keep the polite defaults (rate limit, honest User-Agent suffix, cache first).
* Type hints everywhere (`mypy` runs in strict mode). Match the surrounding style.
* Unit tests must not touch the network; put real-server checks in `tests/live`.
* Prefer archive files over live website JSON whenever both exist.

## Releasing (maintainers)

1. Bump `src/bhavpy/_version.py` and add a CHANGELOG entry.
2. Either push a tag `vX.Y.Z`, **or** open *Actions → release → Run workflow* and type
   the tag. The workflow checks the version matches, builds, publishes to PyPI with
   trusted publishing and creates the GitHub release.

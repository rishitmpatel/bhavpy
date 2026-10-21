## What changes

## How it was tested
- [ ] `pytest` (unit, offline)
- [ ] `ruff check src tests` and `mypy`
- [ ] `pytest -m live tests/live -k ...` if a source changed

## Checklist
- [ ] New/changed parser has a trimmed real fixture in `tests/fixtures/`
- [ ] No code that bypasses blocks/CAPTCHAs; public no-login sources only
- [ ] CHANGELOG entry (user-visible change)

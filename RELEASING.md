# Releasing bhavpy

Publishing uses **PyPI trusted publishing** (OpenID Connect from GitHub Actions), so no
API token is stored anywhere.

## One-time setup

1. **PyPI pending publisher** — sign in at <https://pypi.org>, then
   *Account settings → Publishing → Add a new pending publisher → GitHub*, and enter:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `bhavpy` |
   | Owner | `rishitmpatel` |
   | Repository name | `bhavpy` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   (A *pending* publisher reserves the name and turns into a normal publisher on the
   first successful upload.)
2. **GitHub environment** — in the repo: *Settings → Environments → New environment* →
   name it `pypi`. Optionally add yourself as a required reviewer, so every release waits
   for a click.
3. **GitHub Pages** — after the `Docs` workflow has run once on `main`, go to
   *Settings → Pages → Build and deployment → Deploy from a branch → `gh-pages` / root*.
4. **Labels** (optional; created automatically when first used): `source-broken`,
   `automated`, `good first issue`.

## Each release

1. Update `src/bhavpy/_version.py` (e.g. `0.1.1`) and `CHANGELOG.md`; merge to `main`.
2. Release, either way:
   * **From the browser:** *Actions → release → Run workflow*, type `v0.1.1`, run.
     The workflow creates the tag on that commit.
   * **From a terminal:** `git tag v0.1.1 && git push origin v0.1.1`.
3. The workflow runs lint/type/tests, checks that the tag equals `bhavpy.__version__`,
   builds the sdist and wheel, uploads to PyPI, and creates the GitHub release with the
   files attached.

If the version check fails, fix `_version.py` and run again with the same tag.

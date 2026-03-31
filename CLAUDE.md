# spopy — Development Notes

## Version Bumping

Version appears in three places — update all three:

1. `VERSION` — plain text file
2. `pyproject.toml` — `version = "X.Y.Z"`
3. `spopy.py` — `__version__ = "X.Y.Z"`

## Changelog

Update `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.
Use semantic versioning.

## Releasing

Releases are fully automated. To release a new version:

1. Bump version in all three files (VERSION, pyproject.toml, spopy.py)
2. Update CHANGELOG.md
3. Merge to main

On merge, CI auto-creates a `vX.Y.Z` git tag from the VERSION file,
which triggers the publish workflow to build and push to PyPI.

## Linting

CI runs ruff (check + format) and ty (type check) on all PRs.
Pre-commit config is available for local use: `pre-commit install`.

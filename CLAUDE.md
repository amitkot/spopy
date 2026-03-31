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

Publishing to PyPI is automated via GitHub Actions. To release:

1. Bump version in all three files
2. Update CHANGELOG.md
3. Commit and push to main
4. Tag the commit: `git tag v0.X.Y`
5. Push the tag: `git push origin v0.X.Y`
6. The `publish.yml` workflow builds and publishes to PyPI automatically

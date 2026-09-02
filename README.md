# field-marshall.py

Starter Python app scaffold using Poetry, pytest, pre-commit, and VS Code devcontainers.

## Quickstart

```bash
poetry install --with dev
poetry run poe test
poetry run poe lint
```

## Tooling included

- Poetry packaging and dependency management
- pytest unit testing
- PoeThePoet task runner
- bump-my-version for semantic versioning
- black, isort, and ruff formatting/linting
- pre-commit hook enforcement
- GitHub Actions CI for pre-commit and tests
- GitHub Actions publish workflow for PyPI releases

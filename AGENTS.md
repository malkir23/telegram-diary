# Repository Guidelines

## Project Structure & Module Organization

At the moment, this repository does not contain source files. When code is added, keep the layout explicit and minimal. A recommended baseline:

- `src/` for application code (e.g., `src/api/`, `src/db/`, `src/bot/`).
- `tests/` for automated tests mirroring `src/` structure.
- `scripts/` for local tooling (migrations, seeders, CI helpers).
- `docs/` for architecture notes and API contracts.

If you choose a different structure, document it here and keep paths stable.

## Build, Test, and Development Commands
- `uv` Python package and project manager
- `uvicorn` for local API dev.
- `python -m uvicorn src.api.main:app --reload` for local API dev.
- `pytest` for running tests.
- `ruff check .` / `black .` for linting and formatting.

## Coding Style & Naming Conventions

No linters or formatters are configured yet. When setting them up, document the chosen tools and rules. Suggested defaults for Python projects:

- 4-space indentation, `snake_case` for functions/variables, `PascalCase` for classes.
- Module names in lowercase, tests named `test_*.py`.

## Testing Guidelines

Testing is not configured. Once a framework is added, specify:

- How to run tests (command).
- Test naming patterns.
- Minimum coverage expectations if enforced.

## Commit & Pull Request Guidelines

This directory is not currently a Git repository, so commit conventions can’t be inferred. When Git is initialized, adopt a simple standard (e.g., Conventional Commits) and document it here. For PRs, include:

- Clear description of changes.
- Linked issue (if applicable).
- Screenshots or logs for user-visible changes.

## Configuration & Secrets

Keep secrets out of the repo. Use `.env` or a secrets manager and provide an example file (e.g., `.env.example`) with non-sensitive placeholders.

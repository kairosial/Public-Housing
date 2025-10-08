# Repository Guidelines

## Project Structure & Module Organization

Keep application code inside `src/` using feature-focused packages such as `src/eligibility/` or `src/applications/` so domain logic remains isolated. Co-locate shared utilities under `src/common/`, and reserve `tests/` for mirrors of each module (for example `tests/eligibility/test_rules.py`). Store design references or datasets under `assets/` and capture architectural decisions in `docs/` to keep the root tidy.

## Build, Test, and Development Commands

Expose reproducible workflows through the Makefile: `make setup` should create the virtual environment (`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`), `make start` should run the primary entry point (e.g., `python -m src.app`), and `make test` should execute the suite via `pytest`. When adding CLIs or notebooks, register dedicated targets (for example `make demo-housing` to seed sample data). Document any extra commands in `README.md` after adding them so new contributors can onboard quickly.

## Coding Style & Naming Conventions

Target Python 3.11 and enforce formatting with `black` and import ordering with `isort`; wire both into `pre-commit`. Use 4-space indentation, snake_case for modules/functions, PascalCase for classes, and UPPER_SNAKE_CASE for constants. Keep functions short and domain-driven, and prefer dataclasses or pydantic models for structured records representing residents or housing units.

## Testing Guidelines

Write tests with `pytest`, mirroring the directory structure (`tests/<module>/test_<behavior>.py`), and aim for at least 85% branch coverage measured via `pytest --cov=src`. Include fixtures for sample tenancy records in `tests/fixtures/` to keep scenarios realistic. For new features, add regression tests before refactoring and document edge cases directly in the test names.

## Commit & Pull Request Guidelines

Follow Conventional Commits (`feat:`, `fix:`, `docs:`, etc.) to keep history searchable; scope titles to 72 characters. Reference GitHub issues in the body using `Closes #123` and summarize functional changes plus validation steps. Pull requests should include screenshots or command output when user-facing behavior changes, and a checklist describing testing performed.

## Security & Configuration Tips

Never commit secrets; place sample configuration in `.env.example` and load it via `python-dotenv`. Store encryption keys and API tokens in your password manager, then inject them at runtime through environment variables. Review dependency updates with `pip-compile --upgrade` and note any security-impacting changes in the PR description.

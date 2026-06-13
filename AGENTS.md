# AGENTS.md

This file gives AI coding agents (Claude Code, Cursor, GitHub Copilot
Workspace, etc.) the context they need to work effectively in this
repository. It follows the conventions of [agents.md](https://agents.md/).

## Project overview

FluxPark is a Flask 3 + Flask-SQLAlchemy + Flask-Babel parking management app
for residential and office properties, with SQLite storage and
English/Hindi/Telugu i18n. See [README.md](README.md) for the full feature
list and architecture, and [USER_MANUAL.md](USER_MANUAL.md) for end-user
behaviour.

## Setup commands

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

Run the dev server:

```bash
python app.py        # http://127.0.0.1:5000
```

## Code style

- Formatting/linting: Ruff (`ruff format`, `ruff check`)
- Types: Mypy
- Additional checks: Pylint, Flake8, Bandit (security), Vulture (dead code),
  Pyupgrade
- Config for all of the above lives in `pyproject.toml` (and `.flake8`)
- Run everything with: `pre-commit run --all-files`

## Testing

```bash
pytest
```

- Add/update tests under `tests/` for any behavioural change.
- Coverage must not drop below the `fail_under` threshold in `pyproject.toml`.
- Prefer `app.test_client()`-based tests against real routes/models over
  mocks — this codebase has no migration framework, so tests should create
  their own SQLite database via `db.create_all()`.

## Architecture map

- `app.py` — Flask app instance, configuration, and **all routes/views**
  (this is a large file; use targeted greps rather than reading it whole)
- `models.py` — SQLAlchemy models (`User`, `Property`, `SubRoom`,
  `RoleProfile`, `Vehicle`, `BankDetail`, `ParkingSlot`, `SlotAvailability`,
  `VisitorRequest`, `TransportRequest`, `Notification`, `Transaction`,
  `AISettings`, `AIChatMessage`, ...)
- `extensions.py` — shared `db = SQLAlchemy()` instance
- `constants.py` — shared enums/labels (roles, property types, vehicle types)
- `parking_engine.py` — parking slot generation/allocation logic
- `ai_engine.py` — AI provider integration (local Ollama or BYOK hosted model)
- `templates/` — Jinja2 templates (one file per page/partial; partials are
  prefixed with `_`)
- `translations/<locale>/LC_MESSAGES/` — compiled translations for `en`,
  `hi`, `te`

## Conventions & constraints

- **Sessions**: auth uses `session["user_id"]` and `session["role_profile_id"]`;
  `_require_role_profile()` gates role-scoped routes.
- **Multi-room**: a `User` can have multiple `RoleProfile` rows (one per
  property/company they belong to); the active one is
  `session["role_profile_id"]`. Users switch via "My Rooms"
  (`/rooms`, `/rooms/switch/<id>`, `/rooms/join`).
- **i18n**: every user-facing string must be wrapped in `_()` (or `_l()` for
  module-level/lazy strings). After adding/changing strings, update **all
  three** locales:
  ```bash
  pybabel extract -F babel.cfg -o messages.pot .
  pybabel update -i messages.pot -d translations
  # translate hi/te entries (no fuzzy/empty strings)
  pybabel compile -d translations
  ```
- **Database**: SQLite file at `instance/database.db` (git-ignored). Don't
  commit it. Schema changes go in `models.py`; there is currently no migration
  framework, so existing local databases may need to be deleted during
  development.
- **Secrets**: never hardcode secrets. `SECRET_KEY` comes from the
  `SECRET_KEY` env var (see `.env.example`). Per-user AI provider credentials
  (`AISettings.byok_api_key`, etc.) live in the database, not in code or env
  files.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`,
`fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`, ...) —
`CHANGELOG.md` is generated from these via git-cliff.

## Things to avoid

- Don't commit `instance/`, `.env`, `__pycache__/`, or compiled artifacts.
- Don't bypass `pre-commit`/CI checks (`--no-verify`) without a clear reason
  agreed with the maintainer.
- Don't introduce new runtime dependencies without adding them to
  `requirements.txt` (and dev-only tools to `requirements-dev.txt`).
- Don't leave `fuzzy` or untranslated strings in `hi`/`te` `.po` files.
- Don't hardcode secrets, API keys, or tokens anywhere in the codebase —
  secret scanning (gitleaks) runs in CI and pre-commit.

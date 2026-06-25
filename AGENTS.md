# AGENTS.md

This file gives AI coding agents (Claude Code, Cursor, GitHub Copilot
Workspace, etc.) the context they need to work effectively in this
repository. It follows the conventions of [agents.md](https://agents.md/).

## Project overview

FluxPark is a FastAPI + SQLAlchemy 2.0 parking management app for
residential and office properties, with SQLite storage, an agentic AI
assistant (Google ADK), and English/Hindi/Telugu i18n. See
[README.md](README.md) for the full feature list and architecture, and
[USER_MANUAL.md](USER_MANUAL.md) for end-user behaviour.

It was lifted from an earlier Flask app: a small set of shim modules
(`database.py`, `i18n.py`, `webcompat.py`, `templating.py`) replicate
Flask/Flask-SQLAlchemy/Flask-Babel ergonomics on top of FastAPI/Starlette, so
`models.py`, `parking_engine.py`, `constants.py`, and most templates read
almost like Flask code (`Model.query.filter_by(...)`, `url_for(...)`,
`session[...]`, `flash(...)`) despite running on Starlette underneath.

## Setup commands

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

> `google-adk`'s `litellm` dependency does not yet support Python 3.14 — use
> 3.10–3.13.

Run the dev server:

```bash
uvicorn main:app --reload        # http://127.0.0.1:8000
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
- Prefer `fastapi.testclient.TestClient`-based tests against real
  routes/models over mocks — this codebase has no migration framework, so
  tests create their own SQLite database via `Base.metadata.create_all()`
  (see `tests/conftest.py`).

## Architecture map

- `main.py` — FastAPI app instance, middleware (session, locale,
  `TrustedHostMiddleware`), router includes, startup hook
- `database.py` — SQLAlchemy engine/`scoped_session`/declarative `Base`, with
  `Base.query = SessionLocal.query_property()` so `Model.query.filter_by(...)`
  / `.get(...)` keep working
- `i18n.py` — stdlib-`gettext`-based `_()`/`_l()` shim and locale contextvar
  (replaces Flask-Babel)
- `webcompat.py` — `current_request` contextvar, `url_for()`, `session`,
  `flash()`/`get_flashed_messages()`, `login_required`, `get_or_404()` /
  `first_or_404()` (Flask-parity helpers)
- `templating.py` — `Jinja2Templates` instance, template globals, and
  `render(request, name, **ctx)` (replaces `render_template`)
- `adk_engine.py` — the AI assistant: a Google ADK `Agent` with read/write
  tools backed by the app's own models, a `Runner`-driven reasoning loop, and
  persistent cross-turn memory via `DatabaseSessionService`. Ollama/BYOK/
  Gemini all route through ADK's LiteLLM bridge
- `ai_engine.py` — low-level Ollama/BYOK HTTP helpers used by `adk_engine.py`
  and the AI Settings page's "test connection" feature
- `helpers.py` — shared route helpers: `_require_role_profile()`,
  form-parsing utilities, role-profile label/query helpers
- `models.py` — SQLAlchemy models (`User`, `Property`, `SubRoom`,
  `RoleProfile`, `Vehicle`, `BankDetail`, `ParkingSlot`, `SlotAvailability`,
  `VisitorRequest`, `TransportRequest`, `Notification`, `Transaction`,
  `AISettings`, `AIChatMessage`, ...)
- `constants.py` — shared enums/labels (roles, property types, vehicle types)
- `parking_engine.py` — parking slot generation/allocation logic
- `routers/` — one FastAPI router per feature area (`auth`, `onboarding`,
  `dashboard`, `parking`, `visitors`, `transport`, `security`, `members`,
  `notifications`, `payments`, `ai`) — see README's Project Structure for the
  full breakdown
- `templates/` — Jinja2 templates (one file per page/partial; partials are
  prefixed with `_`)
- `translations/<locale>/LC_MESSAGES/` — compiled translations for `hi`, `te`

## Conventions & constraints

- **Sessions**: auth uses `session["user_id"]` and `session["role_profile_id"]`
  (via `webcompat.session`, a cookie-backed Starlette session proxy);
  `_require_role_profile()` gates role-scoped routes.
- **Routes**: handlers are `async def` (needed for `await request.form()`);
  DB calls go through the synchronous `scoped_session` directly — fine for
  SQLite at this scale, a known/accepted simplification, not a defect.
- **Multi-room**: a `User` can have multiple `RoleProfile` rows (one per
  property/company they belong to); the active one is
  `session["role_profile_id"]`. Users switch via "My Rooms"
  (`/rooms`, `/rooms/switch/{id}`, `/rooms/join`).
- **i18n**: every user-facing string must be wrapped in `_()` (or `_l()` for
  module-level/lazy strings, e.g. in `constants.py`). After adding/changing
  strings, update **both** locales:
  ```bash
  pybabel extract -F babel.cfg -o messages.pot .
  pybabel update -i messages.pot -d translations
  # translate hi/te entries (no fuzzy/empty strings)
  pybabel compile -d translations
  ```
- **Database**: SQLite file at `instance/database.db` (git-ignored). Don't
  commit it. Schema changes go in `models.py`; there is currently no
  migration framework, so existing local databases may need to be deleted
  during development.
- **Secrets**: never hardcode secrets. `SECRET_KEY`/`ALLOWED_HOSTS`/
  `DATABASE_URL` come from env vars (see `.env.example`). Per-user AI provider
  credentials (`AISettings.byok_api_key`, `AISettings.gemini_api_key`, etc.)
  live in the database, not in code or env files.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`,
`fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`, ...) — the `changelog`
CI job generates a changelog from these via git-cliff as a pipeline artifact
(not committed to the repo).

## Things to avoid

- Don't commit `instance/`, `.env`, `__pycache__/`, or compiled artifacts.
- Don't bypass `pre-commit`/CI checks (`--no-verify`) without a clear reason
  agreed with the maintainer.
- Don't introduce new runtime dependencies without adding them to
  `requirements.txt` (and dev-only tools to `requirements-dev.txt`).
- Don't leave `fuzzy` or untranslated strings in `hi`/`te` `.po` files.
- Don't hardcode secrets, API keys, or tokens anywhere in the codebase —
  secret scanning (gitleaks) runs in CI and pre-commit.

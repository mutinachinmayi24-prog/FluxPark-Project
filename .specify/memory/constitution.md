# FluxPark Constitution

This constitution defines the non-negotiable principles for spec-driven
development on FluxPark. Every feature spec, implementation plan, and task
list produced under `specs/` must comply with these principles. Plans that
violate a principle must explain why in a "Complexity Tracking" section and
get explicit sign-off before implementation starts.

## Core Principles

### 1. Spec before code

New features and significant behavioural changes start with a spec under
`specs/<NNN>-<slug>/spec.md` describing the user-facing behaviour, roles
affected, and acceptance criteria — written before any implementation code.
Bug fixes and small refactors do not require a spec.

### 2. Role-aware by design

FluxPark is multi-tenant across **properties** (residential or office),
**companies** (`SubRoom`, office only) and **roles** (`owner`, `tenant`,
`committee`, `security`, `employee`, `manager`). Every spec must state which
roles can access the feature and how data is scoped (per-property, per-company,
or per-user). See `AGENTS.md` for the current role/permission model.

### 3. Internationalisation is not optional

All user-facing strings must be wrapped for translation (`gettext`/`_()`) and
the English, Hindi (`hi`) and Telugu (`te`) catalogs under `translations/`
must be updated (`pybabel extract` → `update` → `compile`) before a feature is
considered done. No fuzzy or empty translations may ship.

### 4. Test what you ship

Every feature spec must include acceptance scenarios that map to automated
tests under `tests/`, using `app.test_client()` against a temporary SQLite
database (see `tests/conftest.py`). Coverage must not regress below the
threshold configured in `pyproject.toml` (`tool.coverage.report.fail_under`).

### 5. Security and secrets

No secrets, API keys, or credentials are committed to the repository.
`SECRET_KEY` and similar configuration come from environment variables
(`.env`, never committed — see `.env.example`). AI assistant credentials
(Ollama/BYOK) are stored per-user in the database via `AISettings`, never in
code or environment files. Gitleaks and Bandit run in CI and pre-commit and
must pass.

### 6. Incremental, reviewable change

Plans should be decomposed into the smallest set of independently reviewable
tasks (see `.specify/templates/tasks-template.md`). Prefer extending existing
patterns (e.g. `RoleProfile`, `generate_parking_slots`, `login_required`) over
introducing new abstractions, unless the spec explicitly justifies the new
abstraction under "Complexity Tracking".

## Governance

This constitution may be amended by updating this file in the same merge
request as the change that motivates the amendment, with the reason recorded
in the commit message (Conventional Commits, so it surfaces in
`CHANGELOG.md`).

**Version**: 1.0.0 | **Ratified**: 2026-06-13 | **Last Amended**: 2026-06-13

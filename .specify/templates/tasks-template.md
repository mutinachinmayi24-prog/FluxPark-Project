# Tasks: [FEATURE NAME]

**Plan**: `specs/[NNN-feature-slug]/plan.md`

Tasks are ordered for incremental, reviewable delivery. Mark each task `[ ]`
pending / `[x]` done. Tasks marked `[P]` can be done in parallel (touch
disjoint files).

## Setup

- [ ] T001 [P] Add/adjust models in `models.py` (if required by the plan)
- [ ] T002 [P] Add constants/config in `constants.py` (if required)

## Core Implementation

- [ ] T003 Implement route(s) in `app.py`
- [ ] T004 Implement/extend helper(s) in `parking_engine.py` / `ai_engine.py`
- [ ] T005 [P] Add/update template(s) under `templates/`

## Internationalisation

- [ ] T006 Wrap new strings with `_()`/`gettext`
- [ ] T007 Run `pybabel extract -F babel.cfg -o messages.pot .`
- [ ] T008 Run `pybabel update -i messages.pot -d translations`
- [ ] T009 Translate new strings for `hi` and `te`, then
      `pybabel compile -d translations`

## Tests

- [ ] T010 [P] Add acceptance tests in `tests/test_<feature>.py` covering each
      scenario from `spec.md`
- [ ] T011 Run `pytest` and confirm coverage threshold in `pyproject.toml`
      is still met

## Polish

- [ ] T012 Run `pre-commit run --all-files` and fix findings
- [ ] T013 Update `CHANGELOG.md` (or rely on `git-cliff` at release time)
- [ ] T014 Update `USER_MANUAL.md` if user-facing behaviour changed

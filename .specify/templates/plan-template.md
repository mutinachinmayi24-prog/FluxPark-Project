# Implementation Plan: [FEATURE NAME]

**Spec**: `specs/[NNN-feature-slug]/spec.md`
**Status**: Draft

## Summary

[1-2 sentences restating the feature from the spec and the chosen technical
approach.]

## Affected Components

| File | Change |
| --- | --- |
| `app.py` | [new/changed routes] |
| `models.py` | [new/changed models or columns] |
| `parking_engine.py` / `ai_engine.py` | [if applicable] |
| `templates/...` | [new/changed templates] |
| `translations/*/LC_MESSAGES/messages.po` | [new strings to translate] |
| `tests/test_....py` | [new tests] |

## Data Model Changes

[Describe any new models / columns / relationships. If none, state "None — no
schema changes required."]

## Step-by-Step Plan

1. [First implementation step]
2. [Next step]
3. ...
4. Update translations (`pybabel extract` → `update` → `compile`) for `en`,
   `hi`, `te`.
5. Add/extend tests in `tests/`.
6. Run `pre-commit run --all-files` and `pytest`.

## Constitution Check

- [ ] Spec exists and acceptance scenarios map to tests (Principle 1, 4)
- [ ] Role/data scoping documented and implemented (Principle 2)
- [ ] i18n updated for en/hi/te (Principle 3)
- [ ] No hardcoded secrets introduced (Principle 5)
- [ ] Reuses existing patterns where possible (Principle 6)

## Complexity Tracking

[Only fill in if a principle above is violated and why. Otherwise: "None."]

| Violation | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| | | |

# Feature Specification: [FEATURE NAME]

**Feature branch**: `[NNN-feature-slug]`
**Status**: Draft
**Input**: [One-paragraph description of the user request that motivated this spec]

## Overview

[2-3 sentences: what is this feature, and why does it matter to the roles
affected?]

## Roles & Scope

| Role | Can access? | Notes |
| --- | --- | --- |
| Owner | | |
| Tenant | | |
| Committee | | |
| Security | | |
| Employee | | |
| Manager | | |

Data scoping: [per-property / per-company (`sub_room_id`) / per-user — be explicit]

## User Scenarios & Acceptance Criteria

### Scenario 1: [short name]

- **Given** [initial state / role / data]
- **When** [user action]
- **Then** [expected outcome]
- **Acceptance test**: `tests/test_<file>.py::test_<name>`

### Scenario 2: [short name]

- **Given** ...
- **When** ...
- **Then** ...
- **Acceptance test**: `tests/test_<file>.py::test_<name>`

## Edge Cases

- [What happens when ... ?]
- [What happens with duplicate / missing / invalid input?]

## Internationalisation

- [ ] All new user-facing strings wrapped with `_()`/`gettext`
- [ ] `pybabel extract`/`update`/`compile` run for `en`, `hi`, `te`
- [ ] No fuzzy or empty translations introduced

## Non-Functional Requirements

- [ ] No new hardcoded secrets (Gitleaks/Bandit pass)
- [ ] No regression in coverage threshold (`pyproject.toml`)

## Out of Scope

- [Explicitly list what this feature does NOT cover]

## Open Questions

- [ ] [Anything marked `[NEEDS CLARIFICATION]` must be resolved before planning]

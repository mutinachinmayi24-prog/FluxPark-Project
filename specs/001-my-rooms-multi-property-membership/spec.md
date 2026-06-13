# Feature Specification: My Rooms (Multi-Property Membership)

**Feature branch**: `001-my-rooms-multi-property-membership`
**Status**: Implemented
**Input**: Users who own/rent/work at more than one property (e.g. they live
in one apartment and are also a committee member of another, or an employee
who also owns a flat) need a way to belong to multiple properties with a
single account and switch between them.

## Overview

A `User` can hold multiple `RoleProfile` records — one per property/company
they belong to, each with its own role (owner, tenant, committee, security,
employee, manager). The "My Rooms" page lists all of a user's role profiles,
lets them switch which one is "active" for the current session, and lets them
join another property via an invite link or code without creating a duplicate
profile.

## Roles & Scope

| Role | Can access? | Notes |
| --- | --- | --- |
| Owner | Yes | Same as all other roles — feature is role-agnostic |
| Tenant | Yes | |
| Committee | Yes | |
| Security | Yes | |
| Employee | Yes | |
| Manager | Yes | |

Data scoping: per-user. `User.role_profiles` is a one-to-many relationship to
`RoleProfile`; `/rooms` only ever lists profiles belonging to
`session["user_id"]`.

## User Scenarios & Acceptance Criteria

### Scenario 1: View my rooms

- **Given** a logged-in user with one or more `RoleProfile` records
- **When** they visit `/rooms`
- **Then** they see one entry per role profile, showing the property name and
  their role in it, with the currently-active one highlighted
- **Acceptance test**: `tests/test_property_residential.py::test_residential_owner_flow`
  (covers the basic `/rooms` page load for a single-room owner)

### Scenario 2: Switch active room

- **Given** a logged-in user with two role profiles (in different properties)
- **When** they `POST /rooms/switch/<role_profile_id>` for the non-active one
- **Then** the session's `role_profile_id`, `property_id` and related keys are
  updated to the selected profile, and they are redirected to `/dashboard`
  showing that property's data
- **Acceptance test**: not yet automated — see Open Questions

### Scenario 3: Join another property via invite link/code

- **Given** a logged-in user who is not yet a member of property X
- **When** they `POST /rooms/join` with a valid invite token/code for property X
- **Then** a new `RoleProfile` is created for them in property X with the
  role encoded in the invite, and they are redirected appropriately
- **Acceptance test**: not yet automated — see Open Questions

### Scenario 4: Re-joining a property you already belong to

- **Given** a logged-in user who already has a `RoleProfile` in property X
- **When** they use an invite link/code for property X again
- **Then** no duplicate `RoleProfile` is created; the user sees an
  "already part of this [property/room]" message (idempotent)
- **Acceptance test**: not yet automated — see Open Questions

## Edge Cases

- Invite token/code is invalid or expired → user sees an error, no
  `RoleProfile` is created.
- User switches to a room that was removed/they were removed from → falls
  back to another of their role profiles, or to `/property-setup` if none
  remain.

## Internationalisation

- [x] All user-facing strings wrapped with `_()`/`gettext`
- [x] `pybabel extract`/`update`/`compile` run for `en`, `hi`, `te`
- [x] No fuzzy or empty translations introduced

## Non-Functional Requirements

- [x] No new hardcoded secrets (Gitleaks/Bandit pass)
- [x] No regression in coverage threshold (`pyproject.toml`)

## Out of Scope

- Cross-property notifications/aggregation (each room's dashboard remains
  independent; only the active room's data is shown at a time).
- Leaving/deleting a room membership (not currently exposed in the UI).

## Open Questions

- [ ] Add automated tests for Scenarios 2-4 (`/rooms/switch/<id>`,
      `/rooms/join`, and the idempotent re-join message) in
      `tests/test_rooms.py`.

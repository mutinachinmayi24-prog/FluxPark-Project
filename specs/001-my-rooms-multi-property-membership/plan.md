# Implementation Plan: My Rooms (Multi-Property Membership)

**Spec**: `specs/001-my-rooms-multi-property-membership/spec.md`
**Status**: Implemented

## Summary

Add a "My Rooms" page backed by the existing `User.role_profiles`
relationship, allowing a user to view all of their role profiles across
properties, switch the active one (stored in the session), and join an
additional property via invite link/code without duplicating profiles.

## Affected Components

| File | Change |
| --- | --- |
| `app.py` | Added `my_rooms` (`/rooms`), `switch_room` (`/rooms/switch/<int:role_profile_id>`, POST) and `join_room` (`/rooms/join`, POST) routes |
| `models.py` | Used existing `User.role_profiles` one-to-many relationship to `RoleProfile` |
| `templates/rooms.html` | New template listing role profiles and a join form |
| `translations/*/LC_MESSAGES/messages.po` | New strings for the My Rooms page |
| `tests/test_property_residential.py` | `/rooms` covered as part of the residential owner onboarding flow |

## Data Model Changes

None — no schema changes required. `RoleProfile.user_id` and
`User.role_profiles` already supported multiple profiles per user.

## Step-by-Step Plan

1. Implement `my_rooms` view: query `RoleProfile.query.filter_by(user_id=session["user_id"])`,
   join to `Property` for display, mark the one matching
   `session["role_profile_id"]` as active.
2. Implement `switch_room`: validate the target `RoleProfile` belongs to the
   current user (404 otherwise), update session keys
   (`role_profile_id`, `property_id`, `role`, etc.), redirect to `/dashboard`.
3. Implement `join_room`: resolve invite token/code to a `Property` + role,
   check for an existing `RoleProfile` for `(user_id, property_id)` — if
   found, flash "already part of this room" and skip creation (idempotent);
   otherwise create a new `RoleProfile` and any required follow-up records.
4. Add `templates/rooms.html` with the room list and join form.
5. Update translations (`pybabel extract` → `update` → `compile`) for `en`,
   `hi`, `te`.
6. Covered `/rooms` in the residential owner end-to-end test; switch/join
   flows remain to be covered (see spec Open Questions).
7. Ran `pre-commit run --all-files` and `pytest`.

## Constitution Check

- [x] Spec exists and acceptance scenarios map to tests (Principle 1, 4) —
      partially: Scenario 1 covered, 2-4 still open
- [x] Role/data scoping documented and implemented (Principle 2) — scoped to
      `session["user_id"]`
- [x] i18n updated for en/hi/te (Principle 3)
- [x] No hardcoded secrets introduced (Principle 5)
- [x] Reuses existing patterns where possible (Principle 6) — reused
      `RoleProfile`/session pattern from initial onboarding

## Complexity Tracking

None.

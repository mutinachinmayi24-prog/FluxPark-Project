# Tasks: My Rooms (Multi-Property Membership)

**Plan**: `specs/001-my-rooms-multi-property-membership/plan.md`

## Setup

- [x] T001 No model changes required — `User.role_profiles` already existed

## Core Implementation

- [x] T002 Implement `my_rooms` view (`/rooms`) in `app.py`
- [x] T003 Implement `switch_room` view (`/rooms/switch/<int:role_profile_id>`, POST) in `app.py`
- [x] T004 Implement `join_room` view (`/rooms/join`, POST) in `app.py`,
      including idempotent "already part of this room" handling
- [x] T005 [P] Add `templates/rooms.html`

## Internationalisation

- [x] T006 Wrap new strings with `_()`/`gettext`
- [x] T007 Run `pybabel extract -F babel.cfg -o messages.pot .`
- [x] T008 Run `pybabel update -i messages.pot -d translations`
- [x] T009 Translate new strings for `hi` and `te`, then
      `pybabel compile -d translations`

## Tests

- [x] T010 [P] Cover `/rooms` page load in
      `tests/test_property_residential.py::test_residential_owner_flow`
- [ ] T011 Add `tests/test_rooms.py` covering `/rooms/switch/<id>`,
      `/rooms/join` (new room), and `/rooms/join` (idempotent re-join message)

## Polish

- [x] T012 Run `pre-commit run --all-files` and fix findings
- [x] T013 Update `CHANGELOG.md` (via `git-cliff` at release time)
- [x] T014 Update `USER_MANUAL.md` — "My Rooms (Multi-Property Membership)"
      section added

# FluxPark Growth Strategy

A plan for growing FluxPark's contributor base beyond the current team. This
is a starting plan, not a record of outcomes — revisit and adjust it as
real outreach happens.

## Outreach plan

- **Lower the barrier to a first contribution.** [Issue templates](.gitlab/issue_templates/)
  (Bug, Feature Request, Documentation, Setup & Dev Environment) and
  [CONTRIBUTING.md](CONTRIBUTING.md) already exist; the next step is
  tagging a real backlog of small, well-scoped issues as `good-first-issue`
  so newcomers have something concrete to pick up instead of facing the
  whole codebase at once.
- **Make non-coding contribution paths visible.** Translation work
  (`translations/hi/`, `translations/te/`, and adding new languages) needs
  no Python knowledge — call this out explicitly in CONTRIBUTING.md as an
  entry point for contributors who aren't developers.
- **Post where contributors already are**: Swecha's own community
  channels/forums (the project is hosted on code.swecha.org), college
  open-source/tech-club communities, and a GitHub mirror so the project is
  discoverable to developers who default to searching GitHub rather than
  GitLab.
- **Show visible signs of an active project.** An automatically generated
  [CHANGELOG.md](CHANGELOG.md) and a green CI pipeline on every push are
  small but real signals that a project is maintained, which matters to
  someone deciding whether to invest time contributing.

## Week-wise plan

| Week | Focus |
|---|---|
| 1 | Triage the codebase for small, self-contained gaps; label 8-10 of them `good-first-issue` with enough context to start without asking questions |
| 2 | Post the project on Swecha community channels and a couple of college open-source/tech-club groups, with a short demo (screenshots or a short recording of the signup → dashboard → AI assistant flow) |
| 3 | Reach out individually to 3-5 people who've shown interest, offer to pair on their first PR |
| 4 | Review and merge first external contributions; capture friction points (unclear docs, missing setup steps) and fix CONTRIBUTING.md/AGENTS.md based on what actually confused people |
| 5-6 | Open up translation contribution as a structured task (a template `.po` file + clear instructions) for non-coding contributors |
| 7-8 | Re-assess: which channels actually produced contributors, double down on those, drop the ones that didn't |

## Geographical expansion plans

FluxPark currently supports English, Hindi, and Telugu. The most honest
near-term "geographical expansion" available to a project at this stage is
**linguistic expansion that maps directly to specific regions**, not
broad simultaneous multi-region rollout:

- Hindi already covers the largest contiguous user base across northern/
  central India.
- Telugu covers Telangana and Andhra Pradesh.
- The next reasonable languages to add, in order of marginal reach per
  effort, are Tamil (Tamil Nadu), Kannada (Karnataka), Marathi
  (Maharashtra), and Bengali (West Bengal/parts of the Northeast) — each
  added the same way Hindi/Telugu were (via `translations/<locale>/`,
  using `pybabel`), and each is a natural first contribution for a speaker
  of that language.
- Beyond language, FluxPark's actual deployment model (residential
  societies, gated communities, office buildings) is inherently local —
  growth looks like one property/college campus/office at a time adopting
  it, not a single national rollout. College hostels and small gated
  communities are the most realistic first real-world pilots, given the
  team's own context.

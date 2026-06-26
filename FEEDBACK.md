# User Feedback Loop

How feedback actually reaches the team and turns into changes, using the
mechanisms that exist in the app and repo today rather than a hypothetical
process.

## Where feedback comes from

1. **AI assistant ratings.** Every assistant reply in the chat has thumbs
   up/down buttons (`templates/ai_assistant.html`), saved on
   `AIChatMessage.feedback` (`models.py`). This is real, structured signal
   on which answers actually helped, tied to the exact message and the
   FAQ/tool lookup that produced it.
2. **Issue reports.** [.gitlab/issue_templates/](.gitlab/issue_templates/)
   gives users/contributors a Bug Report and Feature Request template with
   the fields needed to act on a report without back-and-forth (steps to
   reproduce, expected vs. actual behavior, role/property type affected).
3. **Direct use of the app.** Because every role (Owner, Tenant, Committee,
   Security, Employee, Manager) has a narrow, specific workflow, friction
   shows up as a stalled flow (e.g. a visitor request stuck `pending`, a
   slot that won't list as available) — these are the things to watch for
   directly in usage, not just wait for someone to report.

## Acting on it

| Cadence | Action |
|---|---|
| Weekly | Pull AIChatMessage rows with `feedback = "down"`, read what was actually asked vs. answered. If the gap is a missing FAQ entry, add it to `data/fluxpark_faq_corpus.json` (the assistant's `search_faq_corpus` tool picks it up immediately — no redeploy of a model needed, see `faq_search.py`). If the gap is a missing tool (the agent literally can't do something), that's a feature, not a content fix — goes to the issue tracker. |
| Per issue | New GitLab issues get a label (`bug`, `feature`, `docs`) and a rough severity within 48h of being filed, so reporters get a visible response even before a fix lands. |
| Per release | CHANGELOG.md (generated via git-cliff) is the visible record that feedback turned into something — a contributor or user can see their reported issue's fix land in a dated entry. |

## What this deliberately doesn't claim

There's no user research team, no scheduled user interviews, and no
analytics dashboard — those would be fabricated processes for a project at
this stage. What's described above is the actual mechanism: thumbs-up/down
data the app already collects, and an issue tracker already set up with
templates, both real and running today.

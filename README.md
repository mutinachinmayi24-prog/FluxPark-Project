# FluxPark

FluxPark is a FastAPI-based parking management platform for residential
communities (apartments, gated communities) and office buildings. It handles
phone/OTP-based onboarding, role-based dashboards, parking slot management and
live availability, visitor and transport workflows, payments, in-app
notifications, and a built-in agentic AI assistant — with full multi-language
support (English, Hindi, Telugu).

## Features

- **Phone + OTP signup** and role-based onboarding — Owner, Tenant, Committee,
  Security for residential properties; Employee, Manager, Security for office
  properties
- **Multi-room membership** — a single account can belong to multiple
  properties/companies and switch between them from "My Rooms"
- **Property setup** for residential (apartment / gated community) and office
  (multi-company) layouts
- **Parking slot management** — auto-generated slot numbering, a live
  availability map, and an editable parking layout for owners/committee/managers
- **Visitor management** — visitor passes, visitor requests, visitor logs, and
  unexpected-visitor handling for security staff
- **Transport requests & passes** for office employees
- **Payments** tracking
- **Notifications** centre for all roles
- **Invite links** for onboarding new members into a property/company
- **AI Assistant** — an agent built on Google's [Agent Development
  Kit](https://google.github.io/adk-docs/) that can look up a user's parking
  slots, visitor requests, payments, and notifications, and submit a visitor
  request on their behalf. Supports a local Ollama provider, a Bring-Your-Own-
  Key (BYOK) OpenAI-compatible host, or Google Gemini, configurable per user.
  Each provider's data-handling/openness is disclosed in AI Settings, and the
  chat UI explains what's stored and how to clear it
- **Installable PWA** — a web app manifest + service worker cache the app
  shell and all CSS/JS/font assets (self-hosted, no third-party CDN) for
  faster repeat loads on slow connections, network-first caching of
  dashboard/parking/notifications pages (with an offline banner) so the
  last-known state is still visible with no connection, and a friendly
  offline page instead of a browser error when navigation requests fail
- **Gzip response compression** on every response — ~70-87% smaller
  transfers for HTML pages and vendored CSS/JS on slow connections
- **Internationalisation** — English, Hindi (हिन्दी) and Telugu (తెలుగు)

## Tech Stack

- **Backend**: Python 3, [FastAPI](https://fastapi.tiangolo.com/) on
  [Uvicorn](https://www.uvicorn.org/)
- **ORM / Database**: SQLAlchemy 2.0 on SQLite (`instance/database.db`)
- **AI**: [Google ADK](https://google.github.io/adk-docs/) with a LiteLLM
  bridge to Ollama / any OpenAI-compatible host / Gemini
- **i18n**: stdlib `gettext` reading Babel-compiled `.mo` translations
- **QR codes**: `qrcode` + `Pillow`
- **Frontend**: Jinja2 templates, Bootstrap-based UI, vanilla JS

## Project Structure

```
fluxpark-project/
├── main.py                # FastAPI app instance, middleware, router includes, startup
├── database.py            # SQLAlchemy engine/session/Base shim (Model.query.filter_by(...) style)
├── i18n.py                 # gettext-based _()/_l() shim, locale contextvar
├── templating.py            # Jinja2Templates, render(), template globals
├── webcompat.py               # current_request, url_for, session, flash, login_required, 404 helpers
├── adk_engine.py                # Google ADK agent: instructions, tools, Runner, session memory
├── ai_engine.py                   # Ollama/BYOK HTTP helpers used by adk_engine.py and AI Settings
├── helpers.py                      # Shared route helpers (role-profile guards, form parsing, ...)
├── models.py                        # SQLAlchemy models (User, Property, RoleProfile, ParkingSlot, ...)
├── constants.py                      # Shared enums/labels (roles, property types, vehicle types, ...)
├── parking_engine.py                  # Parking slot generation and allocation logic
├── routers/                            # FastAPI routers, one module per feature area
│   ├── auth.py                          # signup, OTP, logout, invite links, language switch
│   ├── onboarding.py                     # property setup, role forms
│   ├── dashboard.py                       # dashboard, profile, multi-room switching
│   ├── parking.py                          # parking slots, map, availability
│   ├── visitors.py                          # visitor requests, visitor log + CSV, visitor pass/QR
│   ├── transport.py                          # transport requests, transport pass/QR
│   ├── security.py                            # QR scan, entry/exit, unexpected visitors
│   ├── members.py                              # members list/remove, CSV export
│   ├── notifications.py                         # notifications, visitor approve/deny
│   ├── payments.py                                # payments list, mark paid
│   └── ai.py                                       # AI assistant chat + AI settings
├── babel.cfg               # Babel extraction configuration
├── messages.pot             # Translation template
├── translations/              # Compiled translations (hi, te)
├── templates/                   # Jinja2 templates
├── static/                         # CSS / JS / images
│   ├── vendor/                      # Self-hosted Bootstrap, Bootstrap Icons, html5-qrcode (no CDN)
│   ├── icons/                        # PWA app icons
│   ├── manifest.json                  # PWA web app manifest
│   └── js/service-worker.js            # Caches static assets, offline-page fallback
├── instance/                          # Local SQLite database (git-ignored)
├── data/                               # FAQ corpus (en/hi/te), held-out eval set, fine-tuning report
├── scripts/                             # Standalone ML/corpus scripts, see scripts/README.md
├── corpus-export/                        # FAQ corpus exported for Swecha Corpus CLI upload
├── docs/lighthouse/                       # Lighthouse performance/accessibility reports
├── .gitlab/issue_templates/           # Bug / Feature / Documentation / Setup issue templates
├── Dockerfile               # Production image (uvicorn)
├── Dockerfile.ci              # CI-only image with requirements-dev.txt baked in
├── requirements.txt           # Runtime dependencies
└── requirements-dev.txt        # Development / tooling dependencies
```

## Getting Started

### Prerequisites

- Python 3.10–3.13 (`google-adk`'s `litellm` dependency does not yet support
  3.14)
- pip / venv

### Installation

```bash
git clone https://code.swecha.org/chinmayi_08/fluxpark-project.git
cd fluxpark-project
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and adjust values for your environment:

```bash
cp .env.example .env
```

| Variable        | Description                                          | Default                                  |
|------------------|-------------------------------------------------------|-------------------------------------------|
| `SECRET_KEY`     | Session-signing key                                    | `dev-secret-key-change-in-production`     |
| `DATABASE_URL`   | SQLAlchemy database URL                                  | `sqlite:///instance/database.db`          |
| `ALLOWED_HOSTS`  | Comma-separated hostnames `TrustedHostMiddleware` accepts | `*` (unrestricted — set this in production) |

> The SQLite database lives at `instance/database.db` and is created
> automatically on startup.
>
> Per-user AI provider settings (Ollama host/model, BYOK base URL/key/model,
> or Gemini key/model) are configured from the in-app "AI Settings" page and
> stored in the database (`AISettings` in `models.py`) — they are not read
> from environment variables.

### Running the app

```bash
uvicorn main:app --reload
```

The app starts on `http://127.0.0.1:8000`.

### Running with Docker

```bash
docker build -t fluxpark .
docker run -p 8000:8000 --env-file .env -v fluxpark-data:/app/instance fluxpark
```

## Internationalisation

Translations live under `translations/<locale>/LC_MESSAGES/`. After adding or
changing translatable strings:

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
# edit the .po files for hi / te
pybabel compile -d translations
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

## CI/CD

`.gitlab-ci.yml` runs a 5-stage pipeline (lint, security, test, compliance,
changelog) against `Dockerfile.ci`, a locally-built image with
`requirements-dev.txt` baked in — see [CONTRIBUTING.md](CONTRIBUTING.md#cicd-runner)
for how to register and run a local GitLab Runner.

## Documentation

- [User Manual](USER_MANUAL.md) — end-user guide to FluxPark's features
- [Contributing Guide](CONTRIBUTING.md) — development workflow, code style, PR process
- [AGENTS.md](AGENTS.md) — guidance for AI coding agents working in this repo
- [Changelog](CHANGELOG.md) — generated from commit history with git-cliff
- [ML/corpus scripts](scripts/README.md) — FAQ-retrieval fine-tuning (with
  before/after metrics) and Swecha Corpus CLI export
- [Lighthouse report](docs/lighthouse/README.md) — performance/accessibility
  audit under simulated mobile + slow-network conditions
- [Security Policy](SECURITY.md) — how to report vulnerabilities

## License

FluxPark is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-or-later).

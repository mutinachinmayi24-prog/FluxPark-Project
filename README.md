# FluxPark

FluxPark is a Flask-based parking management platform for residential
communities (apartments, gated communities) and office buildings. It handles
phone/OTP-based onboarding, role-based dashboards, parking slot management and
live availability, visitor and transport workflows, payments, in-app
notifications, and a built-in AI assistant — with full multi-language support
(English, Hindi, Telugu).

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
- **AI Assistant** with a local Ollama provider or a Bring-Your-Own-Key (BYOK)
  hosted provider, configurable per user
- **Internationalisation** — English, Hindi (हिन्दी) and Telugu (తెలుగు) via
  Flask-Babel

## Tech Stack

- **Backend**: Python 3, [Flask 3](https://flask.palletsprojects.com/)
- **ORM / Database**: Flask-SQLAlchemy on SQLite (`instance/database.db`)
- **i18n**: Flask-Babel / Babel
- **QR codes**: `qrcode` + `Pillow`
- **Frontend**: Jinja2 templates, Bootstrap-based UI, vanilla JS

## Project Structure

```
fluxpark-project/
├── app.py                # Flask application: config, routes/views
├── models.py              # SQLAlchemy models (User, Property, RoleProfile, ParkingSlot, ...)
├── extensions.py          # Shared Flask extension instances (db = SQLAlchemy())
├── constants.py           # Shared enums/labels (roles, property types, vehicle types, ...)
├── parking_engine.py      # Parking slot generation and allocation logic
├── ai_engine.py           # AI provider integration (Ollama / BYOK)
├── babel.cfg              # Babel extraction configuration
├── messages.pot           # Translation template
├── translations/          # Compiled translations (en, hi, te)
├── templates/             # Jinja2 templates
├── static/                # CSS / JS / images
├── instance/              # Local SQLite database (git-ignored)
├── requirements.txt       # Runtime dependencies
└── requirements-dev.txt   # Development / tooling dependencies
```

## Getting Started

### Prerequisites

- Python 3.11+
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

| Variable     | Description                | Default                                  |
|--------------|-----------------------------|-------------------------------------------|
| `SECRET_KEY` | Flask session signing key   | `dev-secret-key-change-in-production`     |

> The SQLite database lives at `instance/database.db` and is created
> automatically on first run.

### Running the app

```bash
python app.py
```

The app starts on `http://127.0.0.1:5000` (and `0.0.0.0:5000`) in debug mode.

### Running with Docker

```bash
docker build -t fluxpark .
docker run -p 5000:5000 --env-file .env -v fluxpark-data:/app/instance fluxpark
```

## Internationalisation

Translations live under `translations/<locale>/LC_MESSAGES/`. After adding or
changing translatable strings:

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
# edit the .po files for en / hi / te
pybabel compile -d translations
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

## Documentation

- [User Manual](USER_MANUAL.md) — end-user guide to FluxPark's features
- [Contributing Guide](CONTRIBUTING.md) — development workflow, code style, PR process
- [AGENTS.md](AGENTS.md) — guidance for AI coding agents working in this repo
- [Security Policy](SECURITY.md) — how to report vulnerabilities
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## License

FluxPark is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-or-later).

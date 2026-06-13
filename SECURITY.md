# Security Policy

## Supported Versions

FluxPark is currently pre-1.0 and developed on a single `main` branch.
Security fixes are applied to the latest commit on `main`.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| < 0.1.0 | :x:                 |

## Reporting a Vulnerability

**Please do not open a public issue for security vulnerabilities.**

Instead, report it privately by emailing:

**ramyasakhamudi@gmail.com** <!-- TODO: replace with the project's dedicated security contact, if different -->

Please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept code/requests if possible)
- The affected version/commit

You can expect an acknowledgement within **5 business days**. We'll work with
you to understand and address the issue, and we'll credit reporters (unless
you prefer to remain anonymous) once a fix is released.

## Scope

This policy covers the FluxPark application source code in this repository,
including:

- Authentication / OTP flow and session management
- Role-based access control across properties, companies, and rooms
- Parking, visitor, transport, and payment data handling
- AI assistant integration (Ollama / BYOK) and stored provider credentials

Out of scope:

- Third-party dependencies (please report upstream to the relevant project)
- The Flask development server (`app.run(debug=True, ...)`), which must never
  be used in production — see the [Dockerfile](Dockerfile) for a
  production-style WSGI setup

## Disclosure

We follow coordinated disclosure: please give us a reasonable amount of time
to investigate and release a fix before any public disclosure.

## Secret Scanning & Dependency Audits

This repository runs automated secret scanning (gitleaks) and dependency
vulnerability audits (`pip-audit`) via pre-commit hooks and CI
(`.gitlab-ci.yml`). If either flags something in your change, resolve it
before merging — do not suppress findings without justification in the merge
request description.

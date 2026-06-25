# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Bug Fixes

- Unblock pipeline stuck pending with no matching runners
- Make lint/security pipeline jobs actually pass
- Pyupgrade job never actually checked any files
- Jobs timing out on dependency install, not the actual checks
- Pip-licenses job picked up dev-tool licenses via the shared image

### Documentation

- Fix README/CONTRIBUTING/AGENTS.md/.env.example for the FastAPI migration

### Features

- Add a compliance stage with dependency license auditing

### Miscellaneous Tasks

- Add Render Blueprint for one-click deployment
- Bring lint/type/security tooling up to date with the FastAPI migration

### Styling

- Remove stray blank line in members template

## [0.1.0] - 2026-06-13

### Miscellaneous Tasks

- Add dev dependencies for linting
- Add pre-commit config for automated linting
- Add tooling, security, CI and spec-kit scaffolding for compliance



# Contributing to FluxPark

Thanks for your interest in contributing to FluxPark! This document covers how
to set up your development environment, the workflow we follow, and what we
expect from merge requests.

## Development setup

```bash
git clone https://code.swecha.org/chinmayi_08/fluxpark-project.git
cd fluxpark-project
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pre-commit install
```

`requirements-dev.txt` installs the runtime dependencies plus the project's
linting, type-checking, security, and testing tools (Ruff, Mypy, Pylint,
Flake8, Bandit, Vulture, Pyupgrade, pytest, pytest-cov).

## Running the app

```bash
uvicorn main:app --reload
```

The app starts at `http://127.0.0.1:8000` using a local SQLite database at
`instance/database.db` (created automatically on startup).

## Branching & commits

- Create a feature branch off `main`: `git checkout -b feat/short-description`
- Write commit messages following
  [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`, ...) — these
  drive `CHANGELOG.md`, generated with [git-cliff](https://git-cliff.org/).
  Before opening a merge request, regenerate it:
  ```bash
  docker run --rm -v "$(pwd):/app" -w /app --entrypoint "" orhunp/git-cliff:latest git-cliff -o CHANGELOG.md
  ```
  (the `changelog` CI job also runs this on every push to `main` and uploads
  the result as a pipeline artifact, as a backup/verification.)
- Keep commits focused and the diff reviewable.

## Code style & quality

Before opening a merge request, run:

```bash
ruff check .
ruff format --check .
mypy .
pylint adk_engine.py ai_engine.py constants.py database.py helpers.py i18n.py main.py models.py parking_engine.py templating.py webcompat.py routers
flake8 .
bandit -c pyproject.toml -r .
vulture
```

Or simply run everything (including secret scanning) via pre-commit:

```bash
pre-commit run --all-files
```

All of the above are configured in `pyproject.toml` / `.flake8` and enforced in
CI (`.gitlab-ci.yml`).

## Tests & coverage

```bash
pytest
```

Coverage must stay at or above the `fail_under` threshold configured in
`pyproject.toml`. Add or update tests under `tests/` for any behavioural
change.

## Internationalisation

FluxPark supports English, Hindi, and Telugu. If you add or change a
user-facing string (wrapped in `_()` / `_l()`):

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
# translate the new/updated entries in translations/{hi,te}/LC_MESSAGES/messages.po
pybabel compile -d translations
```

Do not leave `fuzzy` or empty translation entries in `hi`/`te` for merged
changes.

## Spec-driven development

Non-trivial features should start with a spec under `specs/` (see `.specify/`
for the project constitution and templates) before implementation.

## CI/CD runner

`.gitlab-ci.yml` jobs are untagged, so any runner with "run untagged jobs"
enabled will pick them up. If pipelines sit in **pending** with "no matching
runners available", this project has no runner registered/online on
code.swecha.org yet — that's an infrastructure gap, not a YAML bug, and no
amount of editing the pipeline file will fix it.

Two things to check, in order:

1. **Shared runners enabled?** Project → Settings → CI/CD → Runners. If your
   GitLab group provides shared runners, just enabling them here is enough.
2. **No shared runners available?** Register a project runner yourself:
   ```bash
   GITLAB_PAT=<your PAT with api scope> ./scripts/setup-gitlab-runner.sh
   ```
   Run it from inside the repo (it detects the project URL from `git remote
   get-url origin`), or pass `--url <repo-url>` explicitly. It installs
   `gitlab-runner` if missing, registers a runner against this project via
   the GitLab API, and starts it (systemd/Homebrew service, or a background
   process otherwise). On Windows, run it under WSL or Git Bash. See the
   script's header comment (`--help`) for all options. Get a PAT from
   *User Settings → Access Tokens* with the `api` scope — never commit it or
   paste it into a chat/issue.

## Merge requests

1. Make sure `pre-commit run --all-files` and `pytest` pass locally.
2. Regenerate `CHANGELOG.md` (see Branching & commits above) and include it
   in your commit — don't hand-edit it.
3. Describe the change, its motivation, and how you tested it.
4. Link any related issues.

## Reporting bugs / security issues

- Functional bugs: open an issue describing the bug, steps to reproduce, and
  expected vs. actual behaviour.
- Security issues: **do not** open a public issue — see
  [SECURITY.md](SECURITY.md).

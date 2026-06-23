#!/usr/bin/env bash
# setup-gitlab-runner.sh
# Registers and starts a GitLab Runner for a project — fully automatic.
#
# Usage (from inside a git repo):
#   ./setup-gitlab-runner.sh
#
# Usage (with explicit repo URL):
#   ./setup-gitlab-runner.sh --url https://gitlab.com/mygroup/myrepo
#
# Required:
#   GITLAB_PAT  — Personal Access Token with api scope
#                 (User → Preferences → Access Tokens)
#               Pass via env or --pat flag; script will prompt if missing.
#
# Optional env vars / flags:
#   GITLAB_HOST           — default: inferred from URL / https://gitlab.com
#   RUNNER_EXECUTOR       — shell | docker (default: shell)
#   RUNNER_DOCKER_IMAGE   — default: alpine:latest (docker executor only)
#   RUNNER_TAG_LIST       — comma-separated tags
#
# Windows users:
#   Run this script under WSL or Git Bash (curl and git must be in PATH).
#   The runner will be registered to the WSL/Git Bash environment, not Windows
#   natively — which is usually what you want for CI workloads.

set -euo pipefail

# ─── Defaults ────────────────────────────────────────────────────────────────
GITLAB_HOST="${GITLAB_HOST:-https://gitlab.com}"
GITLAB_PAT="${GITLAB_PAT:-}"
RUNNER_EXECUTOR="${RUNNER_EXECUTOR:-shell}"
RUNNER_DOCKER_IMAGE="${RUNNER_DOCKER_IMAGE:-alpine:latest}"
RUNNER_TAG_LIST="${RUNNER_TAG_LIST:-}"
CONFIG_DIR="${CONFIG_DIR:-$HOME/.gitlab-runner}"

# ─── Colours ─────────────────────────────────────────────────────────────────
# NOTE: All diagnostic output goes to STDERR (>&2). This is essential: several
# of these helpers are called inside functions whose STDOUT is captured via
# command substitution (e.g. RUNNER_TOKEN=$(create_runner_token ...)). If they
# wrote to stdout, the log lines — including ANSI escape codes — would be
# captured into the token and produce:
#   net/http: invalid header field value for "Runner-Token"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*" >&2; }
success() { echo -e "${GREEN}[OK]${NC}    $*" >&2; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*" >&2; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ─── Argument parsing ─────────────────────────────────────────────────────────
REPO_URL_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url|-u)       REPO_URL_ARG="$2";       shift 2 ;;
    --pat|-p)       GITLAB_PAT="$2";         shift 2 ;;
    --host|-H)      GITLAB_HOST="$2";        shift 2 ;;
    --executor|-e)  RUNNER_EXECUTOR="$2";    shift 2 ;;
    --image|-i)     RUNNER_DOCKER_IMAGE="$2"; shift 2 ;;
    --tags)         RUNNER_TAG_LIST="$2";    shift 2 ;;
    --help|-h)
      grep '^#' "$0" | head -25 | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) die "Unknown argument: $1  (run with --help)" ;;
  esac
done

# ─── Resolve project URL ──────────────────────────────────────────────────────
resolve_project_url() {
  if [[ -n "$REPO_URL_ARG" ]]; then
    echo "$REPO_URL_ARG"; return
  fi
  if git rev-parse --git-dir &>/dev/null; then
    local remote
    remote=$(git remote get-url origin 2>/dev/null || true)
    if [[ -n "$remote" ]]; then
      remote=$(echo "$remote" | sed -E \
        's|^git@([^:]+):(.+)\.git$|https://\1/\2|; s|\.git$||')
      echo "$remote"; return
    fi
  fi
  die "Could not determine project URL.\n  Run from inside a git repo or pass --url <repo-url>"
}

# ─── Install gitlab-runner ────────────────────────────────────────────────────

# Install the static binary directly — works on any Linux distro/arch.
# Called as a fallback when a package-manager installation fails or is
# unavailable.  Also sets up the gitlab-runner system user.
_install_binary_linux() {
  local arch="$1"
  local bin_url="https://gitlab-runner-downloads.s3.amazonaws.com/latest/binaries/gitlab-runner-linux-${arch}"
  info "Falling back to static binary for linux/$arch ..."
  sudo curl -fsSL "$bin_url" -o /usr/local/bin/gitlab-runner
  sudo chmod +x /usr/local/bin/gitlab-runner
  sudo useradd --system --shell /bin/false \
    --create-home --home-dir /var/lib/gitlab-runner \
    gitlab-runner 2>/dev/null || true
  success "gitlab-runner installed to /usr/local/bin/gitlab-runner"
}

install_gitlab_runner() {
  info "Installing gitlab-runner..."

  # ── macOS ──────────────────────────────────────────────────────────────────
  if [[ "$OSTYPE" == "darwin"* ]]; then
    if command -v brew &>/dev/null; then
      brew install gitlab-runner && brew services start gitlab-runner
    else
      die "Homebrew not found. Install it from https://brew.sh then re-run."
    fi
    return
  fi

  # ── Linux: resolve architecture once ──────────────────────────────────────
  local arch
  arch=$(uname -m)
  case "$arch" in
    x86_64)  arch="amd64" ;;
    aarch64) arch="arm64" ;;
    armv7l)  arch="arm"   ;;
    *) die "Unsupported architecture: $arch" ;;
  esac

  # ── Debian / Ubuntu (apt) ─────────────────────────────────────────────────
  if command -v apt-get &>/dev/null; then
    info "Detected apt — trying GitLab package repo..."
    if curl -fsSL https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh \
         | sudo bash \
       && sudo apt-get install -y gitlab-runner; then
      success "Installed via apt."
      return
    fi
    warn "apt installation failed — falling back to binary."
    _install_binary_linux "$arch"
    return
  fi

  # ── RHEL / CentOS / Fedora (dnf / yum) ───────────────────────────────────
  if command -v dnf &>/dev/null || command -v yum &>/dev/null; then
    local pm; command -v dnf &>/dev/null && pm=dnf || pm=yum
    info "Detected $pm — trying GitLab package repo..."
    if curl -fsSL https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.rpm.sh \
         | sudo bash \
       && sudo "$pm" install -y gitlab-runner; then
      success "Installed via $pm."
      return
    fi
    warn "$pm installation failed — falling back to binary."
    _install_binary_linux "$arch"
    return
  fi

  # ── openSUSE / SLES (zypper) ──────────────────────────────────────────────
  if command -v zypper &>/dev/null; then
    info "Detected zypper — trying GitLab RPM repo..."
    local rpm_url="https://packages.gitlab.com/runner/gitlab-runner/el/8/${arch}/gitlab-runner-latest.${arch}.rpm"
    local tmp_rpm; tmp_rpm=$(mktemp /tmp/gitlab-runner-XXXX.rpm)
    if curl -fsSL "$rpm_url" -o "$tmp_rpm" \
       && sudo zypper --non-interactive install --allow-unsigned-rpm "$tmp_rpm"; then
      rm -f "$tmp_rpm"
      success "Installed via zypper."
      return
    fi
    rm -f "$tmp_rpm"
    warn "zypper installation failed — falling back to binary."
    _install_binary_linux "$arch"
    return
  fi

  # ── Arch Linux (pacman) ───────────────────────────────────────────────────
  if command -v pacman &>/dev/null; then
    info "Detected pacman — trying AUR helper or community repo..."
    # Try yay/paru (AUR) first, then the official repos (gitlab-runner is in
    # community / extra on most Arch-based distros).
    if command -v yay &>/dev/null && yay -S --noconfirm gitlab-runner; then
      success "Installed via yay."
      return
    elif command -v paru &>/dev/null && paru -S --noconfirm gitlab-runner; then
      success "Installed via paru."
      return
    elif sudo pacman -Sy --noconfirm gitlab-runner 2>/dev/null; then
      success "Installed via pacman."
      return
    fi
    warn "pacman installation failed — falling back to binary."
    _install_binary_linux "$arch"
    return
  fi

  # ── No recognised package manager — go straight to binary ────────────────
  info "No recognised package manager found."
  _install_binary_linux "$arch"
}

# ─── Fetch project ID via GitLab API ─────────────────────────────────────────
get_project_id() {
  local encoded_path
  # Extract "group/repo" from URL and URL-encode the slash as %2F
  encoded_path=$(echo "$PROJECT_URL" \
    | sed "s|${GITLAB_HOST}/||" \
    | sed 's|/|%2F|g')

  local response http_code body
  response=$(curl -sS -w "\n%{http_code}" \
    --header "PRIVATE-TOKEN: $GITLAB_PAT" \
    "${GITLAB_HOST}/api/v4/projects/${encoded_path}")
  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [[ "$http_code" != "200" ]]; then
    local msg; msg=$(echo "$body" | grep -o '"message":"[^"]*"' | head -1 || echo "$body")
    die "Could not fetch project info (HTTP $http_code): $msg\n  Check your PAT has 'api' scope and access to the project."
  fi

  echo "$body" | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*'
}

# ─── Create runner token via API ──────────────────────────────────────────────
create_runner_token() {
  local project_id="$1"
  info "Creating runner token via API for project ID $project_id..."

  local response http_code body
  response=$(curl -sS -w "\n%{http_code}" \
    --request POST \
    --header "PRIVATE-TOKEN: $GITLAB_PAT" \
    --header "Content-Type: application/json" \
    --data "{
      \"runner_type\": \"project_type\",
      \"project_id\": $project_id,
      \"description\": \"$RUNNER_NAME\",
      \"tag_list\": \"$RUNNER_TAG_LIST\",
      \"run_untagged\": true
    }" \
    "${GITLAB_HOST}/api/v4/user/runners")
  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [[ "$http_code" == "201" ]]; then
    local token; token=$(echo "$body" | grep -o '"token":"[^"]*"' | head -1 | cut -d'"' -f4)
    echo "$token"
    return
  fi

  # Fallback: try legacy project runners endpoint (GitLab < 16.0)
  warn "New runner API returned HTTP $http_code, trying legacy endpoint..."
  response=$(curl -sS -w "\n%{http_code}" \
    --request POST \
    --header "PRIVATE-TOKEN: $GITLAB_PAT" \
    --form "id=$project_id" \
    --form "description=$RUNNER_NAME" \
    --form "tag_list=$RUNNER_TAG_LIST" \
    --form "run_untagged=true" \
    "${GITLAB_HOST}/api/v4/projects/${project_id}/runners")
  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [[ "$http_code" == "201" ]]; then
    local token; token=$(echo "$body" | grep -o '"token":"[^"]*"' | head -1 | cut -d'"' -f4)
    echo "$token"
    return
  fi

  local msg; msg=$(echo "$body" | grep -o '"message":"[^"]*"' | head -1 || echo "$body")
  die "Failed to create runner token (HTTP $http_code): $msg"
}

# ─── Start / restart the runner ──────────────────────────────────────────────
start_runner() {
  local config="$1"
  # If installed as a systemd service
  if systemctl list-units --full -all 2>/dev/null | grep -q "gitlab-runner.service"; then
    info "Restarting gitlab-runner systemd service..."
    sudo systemctl restart gitlab-runner
    return
  fi
  # Homebrew on macOS
  if command -v brew &>/dev/null && brew services list 2>/dev/null | grep -q gitlab-runner; then
    info "Restarting gitlab-runner via Homebrew..."
    brew services restart gitlab-runner
    return
  fi
  # Background process (user mode)
  info "Starting gitlab-runner in background (user mode)..."
  mkdir -p "$CONFIG_DIR"
  nohup gitlab-runner run --config "$config" \
    > "$CONFIG_DIR/runner.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$CONFIG_DIR/runner.pid"
  info "Runner PID: $pid  |  Log: $CONFIG_DIR/runner.log"
}

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

PROJECT_URL=$(resolve_project_url)
PROJECT_URL="${PROJECT_URL%/}"  # strip trailing slash

# Infer host from project URL
DERIVED_HOST=$(echo "$PROJECT_URL" | grep -oE '^https?://[^/]+')
GITLAB_HOST="${DERIVED_HOST:-$GITLAB_HOST}"

# Runner name = group-repo
RUNNER_NAME=$(echo "$PROJECT_URL" | sed 's|.*/\([^/]*/[^/]*\)$|\1|' | tr '/' '-')

info "Project  : $PROJECT_URL"
info "GitLab   : $GITLAB_HOST"
info "Executor : $RUNNER_EXECUTOR"
info "Runner   : $RUNNER_NAME"

# ── 1. Ensure gitlab-runner is installed ─────────────────────────────────────
if ! command -v gitlab-runner &>/dev/null; then
  warn "gitlab-runner not found. Attempting to install..."
  install_gitlab_runner
  command -v gitlab-runner &>/dev/null || die "Installation failed — please install gitlab-runner manually."
fi
success "gitlab-runner $(gitlab-runner --version | head -1 | awk '{print $3}')"

# ── 2. Get Personal Access Token ─────────────────────────────────────────────
if [[ -z "$GITLAB_PAT" ]]; then
  echo "" >&2
  echo -e "  ${YELLOW}A Personal Access Token (PAT) with 'api' scope is required${NC}" >&2
  echo "  → ${GITLAB_HOST}/-/user_settings/personal_access_tokens" >&2
  echo "" >&2
  read -rsp "  Paste your GitLab PAT: " GITLAB_PAT
  echo "" >&2
  [[ -z "$GITLAB_PAT" ]] && die "PAT cannot be empty."
fi

# Trim any stray whitespace/newlines that may have crept into the PAT
GITLAB_PAT="$(echo -n "$GITLAB_PAT" | tr -d '[:space:]')"

# ── 3. Fetch project ID ───────────────────────────────────────────────────────
info "Fetching project info..."
PROJECT_ID=$(get_project_id)
success "Project ID: $PROJECT_ID"

# ── 4. Create runner + get its token via API ──────────────────────────────────
RUNNER_TOKEN=$(create_runner_token "$PROJECT_ID")
# Defensive trim: tokens must be clean for use as an HTTP header value
RUNNER_TOKEN="$(echo -n "$RUNNER_TOKEN" | tr -d '[:space:]')"
[[ -z "$RUNNER_TOKEN" ]] && die "Received empty runner token from API."
success "Runner token obtained."

# ── 5. Register the runner ────────────────────────────────────────────────────
RUNNER_CONFIG_FILE="$CONFIG_DIR/config.toml"
mkdir -p "$CONFIG_DIR"

info "Registering runner '${RUNNER_NAME}'..."

REGISTER_ARGS=(
  --non-interactive
  --url              "$GITLAB_HOST"
  --token            "$RUNNER_TOKEN"
  --name             "$RUNNER_NAME"
  --executor         "$RUNNER_EXECUTOR"
  --config           "$RUNNER_CONFIG_FILE"
)

[[ -n "$RUNNER_TAG_LIST" ]] && REGISTER_ARGS+=(--tag-list "$RUNNER_TAG_LIST")
[[ "$RUNNER_EXECUTOR" == "docker" ]] && REGISTER_ARGS+=(--docker-image "$RUNNER_DOCKER_IMAGE")

if gitlab-runner register "${REGISTER_ARGS[@]}"; then
  success "Runner registered."
else
  die "Registration failed. Check the output above for details."
fi

# ── 6. Start the runner ───────────────────────────────────────────────────────
start_runner "$RUNNER_CONFIG_FILE"

echo "" >&2
success "Done! Runner '${RUNNER_NAME}' is registered and running."
echo "" >&2
echo "  ┌─ Next steps ──────────────────────────────────────────────────" >&2
echo "  │  CI/CD settings : $PROJECT_URL/-/settings/ci_cd" >&2
echo "  │  Config file    : $RUNNER_CONFIG_FILE" >&2
echo "  │  Log file       : $CONFIG_DIR/runner.log" >&2
echo "  │" >&2
echo "  │  To stop the background runner:" >&2
echo "  │    kill \$(cat $CONFIG_DIR/runner.pid)" >&2
echo "  └───────────────────────────────────────────────────────────────" >&2
echo "" >&2
#!/usr/bin/env bash
#
# os-lab one-command setup — macOS
#
# Detects the host, reports device status, installs prerequisites via Homebrew,
# fetches or updates the os-lab checkout, provisions a Python virtualenv, and
# launches the web console (PWA UI). Safe to run repeatedly.
#
# Quick start (remote):
#   curl -fsSL https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install-macos.sh | bash
#
# Quick start (from a checkout):
#   ./scripts/setup/install-macos.sh
#
# Options:
#   -d, --dir DIR      install/checkout directory      (default: $HOME/os-lab)
#   -b, --branch NAME  git branch to track             (default: master)
#   -p, --port N       web console port                (default: 5050)
#       --report-only  detect + report only; change nothing
#       --no-install   do not install prerequisites via Homebrew
#       --no-run       set up but do not launch the web console
#       --minimal      virtualenv for the UI only (skip heavy tool deps)
#       --update       pull latest even if the checkout already exists
#   -h, --help         show this help
#
# Environment overrides: OSLAB_REPO, OSLAB_DIR, OSLAB_BRANCH, OSLAB_PORT
set -uo pipefail

OSLAB_REPO="${OSLAB_REPO:-https://github.com/keyvanarasteh/os-lab.git}"
OSLAB_DIR="${OSLAB_DIR:-$HOME/os-lab}"
OSLAB_BRANCH="${OSLAB_BRANCH:-master}"
OSLAB_PORT="${OSLAB_PORT:-5050}"

REPORT_ONLY=0; DO_INSTALL=1; DO_RUN=1; MINIMAL=0; FORCE_UPDATE=0

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; CYAN=$'\033[36m'
  DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; CYAN=""; DIM=""; BOLD=""; RESET=""
fi
info()  { printf '%s==>%s %s\n' "$GREEN" "$RESET" "$*"; }
step()  { printf '%s --%s %s\n' "$CYAN" "$RESET" "$*"; }
warn()  { printf '%swarning:%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
die()   { printf '%serror:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }
ok()    { printf '   %sok%s   %s\n' "$GREEN" "$RESET" "$*"; }
miss()  { printf '   %smiss%s %s\n' "$RED" "$RESET" "$*"; }
hr()    { printf '%s\n' "------------------------------------------------------------"; }

banner() {
  printf '%s' "$BOLD"
  cat <<'EOF'
   ___  ____    _          _
  / _ \/ ___|  | |    __ _| |__
 | | | \___ \  | |   / _` | '_ \
 | |_| |___) | | |__| (_| | |_) |
  \___/|____/  |_____\__,_|_.__/   one-command setup · macOS
EOF
  printf '%s\n' "$RESET"
}
# Self-contained so it works when piped via `curl | bash` (no readable $0).
usage() {
  cat <<'EOF'
os-lab one-command setup — macOS

Usage: install-macos.sh [options]   (or: curl -fsSL .../install-macos.sh | bash)

Options:
  -d, --dir DIR      install/checkout directory      (default: $HOME/os-lab)
  -b, --branch NAME  git branch to track             (default: master)
  -p, --port N       web console port                (default: 5050)
      --report-only  detect + report only; change nothing
      --no-install   do not install prerequisites via Homebrew
      --no-run       set up but do not launch the web console
      --minimal      virtualenv for the UI only (skip heavy tool deps)
      --update       pull latest even if the checkout already exists
  -h, --help         show this help

Environment overrides: OSLAB_REPO, OSLAB_DIR, OSLAB_BRANCH, OSLAB_PORT
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -d|--dir)      OSLAB_DIR="${2:?}"; shift 2 ;;
    -b|--branch)   OSLAB_BRANCH="${2:?}"; shift 2 ;;
    -p|--port)     OSLAB_PORT="${2:?}"; shift 2 ;;
    --report-only) REPORT_ONLY=1; shift ;;
    --no-install)  DO_INSTALL=0; shift ;;
    --no-run)      DO_RUN=0; shift ;;
    --minimal)     MINIMAL=1; shift ;;
    --update)      FORCE_UPDATE=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }
ver()  { "$@" 2>/dev/null | head -n1; }

[ "$(uname -s)" = "Darwin" ] || warn "this script targets macOS; on Linux use install.sh"

HOST_ARCH="$(uname -m 2>/dev/null || echo unknown)"
MACOS_VER="$(sw_vers -productVersion 2>/dev/null || echo unknown)"
CHIP="intel"; [ "$HOST_ARCH" = "arm64" ] && CHIP="apple-silicon"
BREW_PREFIX=""; have brew && BREW_PREFIX="$(brew --prefix 2>/dev/null)"

report_tool() {
  # usage: report_tool LABEL CMD [ARGS...]
  local label="$1"; shift; local bin="$1"
  if have "$bin"; then
    printf '   %sok%s   %-16s %s%s%s  %s%s%s\n' "$GREEN" "$RESET" "$label" \
      "$BOLD" "$("$@" 2>&1 | head -n1)" "$RESET" "$DIM" "$(command -v "$bin")" "$RESET"
    return 0
  fi
  printf '   %smiss%s %-16s %snot found%s\n' "$RED" "$RESET" "$label" "$DIM" "$RESET"
  return 1
}

cpu_cores() { sysctl -n hw.ncpu 2>/dev/null || echo "?"; }
mem_total() { awk -v b="$(sysctl -n hw.memsize 2>/dev/null)" 'BEGIN{ if(b>0) printf "%.1f GiB", b/1073741824; else print "?"}'; }
disk_free() { df -h "$1" 2>/dev/null | awk 'NR==2{print $4" free of "$2}'; }

print_report() {
  hr; info "Host & device report"; hr
  printf '   %-16s %s\n' "OS"        "macOS $MACOS_VER ($CHIP / $HOST_ARCH)"
  printf '   %-16s %s\n' "Provider"  "native-macos (Virtualization.framework / HVF)"
  printf '   %-16s %s\n' "Homebrew"  "${BREW_PREFIX:-not installed}"
  printf '   %-16s %s\n' "CPU cores" "$(cpu_cores)"
  printf '   %-16s %s\n' "Memory"    "$(mem_total)"
  printf '   %-16s %s\n' "Disk"      "$(disk_free "$HOME")"
  printf '   %-16s %snote%s   Windows/Linux VM labs need a KVM Linux host; on macOS use\n' "VM labs" "$YELLOW" "$RESET"
  printf '   %-16s        the Android & iOS tooling (iOS lab supports native Xcode/simctl)\n' ""
  hr; info "Host tools"; hr
  report_tool "git"      git     --version
  report_tool "python3"  python3 --version
  if have pip3; then report_tool "pip" pip3 --version
  else report_tool "pip" pip --version; fi
  report_tool "docker"   docker  --version
  if have docker && docker compose version >/dev/null 2>&1; then
    ok "compose          $(docker compose version 2>/dev/null | head -n1)"
  elif have docker-compose; then
    report_tool "compose" docker-compose --version
  fi
  report_tool "xcode"    xcodebuild -version
  report_tool "simctl"   xcrun   simctl help
  report_tool "adb"      adb     --version
  report_tool "java"     java    -version
  report_tool "node"     node    --version
  hr
}

# Make a Homebrew install visible on PATH in the current shell.
brew_shellenv() {
  local p
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$p" ] && { eval "$("$p" shellenv)" 2>/dev/null || true; return; }
  done
  have brew && eval "$(brew shellenv)" 2>/dev/null || true
}

ensure_prereqs() {
  if ! have brew; then
    if have git && have python3; then
      ok "git and python3 already present; continuing without Homebrew"; return 0
    fi
    step "Homebrew not found — bootstrapping it (non-interactive)"
    NONINTERACTIVE=1 /bin/bash -c \
      "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
      || warn "Homebrew bootstrap reported errors; continuing"
    brew_shellenv
    have brew || {
      have git && have python3 && { ok "prerequisites present despite no brew; continuing"; return 0; }
      die "Homebrew unavailable and git/python3 missing — install Homebrew manually, then re-run"
    }
  fi
  local want=()
  have git     || want+=("git")
  have python3 || want+=("python@3.12")
  if [ "${#want[@]}" -eq 0 ]; then ok "all core prerequisites already present"; return 0; fi
  step "installing via Homebrew: ${want[*]}"
  brew install "${want[@]}" || warn "brew install reported errors; continuing"
  brew_shellenv   # expose newly installed python3/git on PATH for this run
}

REPO_ROOT=""; CLONED=0
locate_or_clone() {
  local here; here="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$here" ] && [ -f "$here/labctl" ] && [ -d "$here/android-lab" ]; then
    REPO_ROOT="$here"; step "using existing checkout: $REPO_ROOT"
  elif [ -d "$OSLAB_DIR/.git" ]; then
    REPO_ROOT="$OSLAB_DIR"; step "found checkout: $REPO_ROOT"
  else
    step "cloning $OSLAB_REPO → $OSLAB_DIR"
    have git || die "git is required to clone"
    git clone --branch "$OSLAB_BRANCH" "$OSLAB_REPO" "$OSLAB_DIR" || die "git clone failed"
    REPO_ROOT="$OSLAB_DIR"; CLONED=1; return 0
  fi
  # Update only a fresh clone or when --update is explicit; never switch branches.
  if [ "$CLONED" -eq 1 ] || [ "$FORCE_UPDATE" -eq 1 ]; then
    local cur; cur="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)"
    step "updating checkout (branch: $cur)"
    git -C "$REPO_ROOT" fetch --quiet origin "$cur" 2>/dev/null || warn "git fetch failed (offline?)"
    # porcelain is empty only when tracked AND untracked trees are clean
    if [ -z "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
      git -C "$REPO_ROOT" pull --quiet --ff-only origin "$cur" 2>/dev/null \
        && ok "updated to $(git -C "$REPO_ROOT" rev-parse --short HEAD)" \
        || warn "could not fast-forward; leaving checkout as-is"
    else
      warn "local changes present; skipping auto-update"
    fi
  fi
}

VENV_DIR=""
provision_venv() {
  VENV_DIR="$REPO_ROOT/.venv"
  local req="$REPO_ROOT/android-lab/lab/requirements.txt"
  brew_shellenv
  local py; py="$(command -v python3 || command -v python || true)"
  [ -n "$py" ] || die "no python interpreter found; install python3 (run without --no-install)"
  if [ ! -d "$VENV_DIR" ]; then
    step "creating virtualenv: $VENV_DIR"; "$py" -m venv "$VENV_DIR" || die "failed to create virtualenv"
  else
    step "reusing virtualenv: $VENV_DIR"
  fi
  # shellcheck disable=SC1091
  . "$VENV_DIR/bin/activate"
  if [ "$MINIMAL" -eq 1 ]; then
    ok "minimal mode — web console runs on the standard library, no extra deps"
    python "$REPO_ROOT/source-lab/run.py" doctor || warn "Source Lab needs Python 3.11+ and writable private storage"
  elif [ -f "$req" ]; then
    python -m pip install --quiet --upgrade pip wheel 2>/dev/null || true
    step "installing tool dependencies (this can take a few minutes)"
    python -m pip install --quiet -r "$req" \
      && ok "tool dependencies installed" \
      || warn "some dependencies failed to build; the web console still runs. Re-run with --minimal to skip."
  else
    warn "requirements.txt not found at $req; skipping"
  fi
}

# --------------------------------------------------------------------------- #
# Dashboard (Astro): rebuild locally when Node 22+ is present, else use the
# committed build in dashboard/dist. Local builds go to the untracked
# dashboard/build so they never dirty the checkout; the console serves the newer.
# --------------------------------------------------------------------------- #
build_dashboard() {
  local dir="$REPO_ROOT/dashboard"
  [ -f "$dir/package.json" ] || return 0
  local prebuilt="prebuilt dashboard (dashboard/dist)"
  [ -f "$dir/dist/index.html" ] || prebuilt="classic console (no dashboard build found)"
  if [ "$MINIMAL" -eq 1 ] || [ "${OSLAB_DASHBOARD_BUILD:-1}" = "0" ]; then
    ok "dashboard: using the $prebuilt"
    return 0
  fi
  local major=0
  have node && major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  if ! have npm || [ "${major:-0}" -lt 22 ]; then
    ok "dashboard: Node.js 22+ not found, using the $prebuilt"
    return 0
  fi
  step "building the dashboard with Node $(node --version) (set OSLAB_DASHBOARD_BUILD=0 to skip)"
  if ( cd "$dir" \
       && { npm ci --no-audit --no-fund >/dev/null 2>&1 || npm install --no-audit --no-fund >/dev/null 2>&1; } \
       && npm run --silent build:local >/dev/null 2>&1 ); then
    ok "dashboard built → dashboard/build"
  else
    warn "dashboard build failed; using the $prebuilt"
  fi
}

launch_ui() {
  local orch="$REPO_ROOT/android-lab/lab/orchestrator.py"
  local url="http://127.0.0.1:$OSLAB_PORT"
  [ -f "$orch" ] || die "web console entrypoint missing: $orch"
  info "Launching os-lab web console → $url"
  step "press Ctrl+C to stop"
  open "$url" >/dev/null 2>&1 &
  exec python "$orch" ui --port "$OSLAB_PORT"
}

banner
print_report
if [ "$REPORT_ONLY" -eq 1 ]; then info "report-only: no changes made"; exit 0; fi
[ "$DO_INSTALL" -eq 1 ] && { info "Checking prerequisites"; ensure_prereqs; }
info "Fetching os-lab"; locate_or_clone
info "Provisioning Python environment"; provision_venv
info "Preparing the dashboard"; build_dashboard
if [ "$DO_RUN" -eq 1 ]; then
  launch_ui
else
  hr
  ok "setup complete — checkout at $REPO_ROOT"
  printf '   start the console later with:\n'
  printf '     %scd %s && . .venv/bin/activate && python android-lab/lab/orchestrator.py ui --port %s%s\n' \
    "$DIM" "$REPO_ROOT" "$OSLAB_PORT" "$RESET"
fi

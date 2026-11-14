#!/usr/bin/env bash
#
# os-lab one-command setup — Linux
#
# Detects the host, reports device status, installs prerequisites, fetches or
# updates the os-lab checkout, provisions a Python virtualenv, and launches the
# web console (PWA UI). Safe to run repeatedly; it updates in place.
#
# Quick start (remote):
#   curl -fsSL https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install.sh | bash
#
# Quick start (from a checkout):
#   ./scripts/setup/install.sh
#
# Options:
#   -d, --dir DIR      install/checkout directory      (default: $HOME/os-lab)
#   -b, --branch NAME  git branch to track             (default: master)
#   -p, --port N       web console port                (default: 5050)
#       --report-only  detect + report only; change nothing
#       --no-install   do not install system prerequisites
#       --no-run       set up but do not launch the web console
#       --minimal      virtualenv for the UI only (skip heavy tool deps)
#       --update       pull latest even if the checkout already exists
#   -h, --help         show this help
#
# Environment overrides: OSLAB_REPO, OSLAB_DIR, OSLAB_BRANCH, OSLAB_PORT
set -uo pipefail

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
OSLAB_REPO="${OSLAB_REPO:-https://github.com/keyvanarasteh/os-lab.git}"
OSLAB_DIR="${OSLAB_DIR:-$HOME/os-lab}"
OSLAB_BRANCH="${OSLAB_BRANCH:-master}"
OSLAB_PORT="${OSLAB_PORT:-5050}"

REPORT_ONLY=0
DO_INSTALL=1
DO_RUN=1
MINIMAL=0
FORCE_UPDATE=0

# --------------------------------------------------------------------------- #
# Pretty output
# --------------------------------------------------------------------------- #
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

banner() {
  printf '%s' "$BOLD"
  cat <<'EOF'
   ___  ____    _          _
  / _ \/ ___|  | |    __ _| |__
 | | | \___ \  | |   / _` | '_ \
 | |_| |___) | | |__| (_| | |_) |
  \___/|____/  |_____\__,_|_.__/   one-command setup · Linux
EOF
  printf '%s\n' "$RESET"
}

# Self-contained so it works when piped via `curl | bash` (no readable $0).
usage() {
  cat <<'EOF'
os-lab one-command setup — Linux

Usage: install.sh [options]   (or: curl -fsSL .../install.sh | bash)

Options:
  -d, --dir DIR      install/checkout directory      (default: $HOME/os-lab)
  -b, --branch NAME  git branch to track             (default: master)
  -p, --port N       web console port                (default: 5050)
      --report-only  detect + report only; change nothing
      --no-install   do not install system prerequisites
      --no-run       set up but do not launch the web console
      --minimal      virtualenv for the UI only (skip heavy tool deps)
      --update       pull latest even if the checkout already exists
  -h, --help         show this help

Environment overrides: OSLAB_REPO, OSLAB_DIR, OSLAB_BRANCH, OSLAB_PORT
EOF
}

# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
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

# --------------------------------------------------------------------------- #
# Host + device detection
# --------------------------------------------------------------------------- #
HOST_OS="linux"
HOST_ARCH="$(uname -m 2>/dev/null || echo unknown)"
HOST_KERNEL="$(uname -r 2>/dev/null || echo unknown)"
HOST_DISTRO="unknown"
PKG=""           # package manager
PKG_INSTALL=""   # install command
PROVIDER="native-linux"

detect_distro() {
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    HOST_DISTRO="${PRETTY_NAME:-${NAME:-linux}}"
  fi
  # WSL detection → VM labs route through the Windows host
  if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
    PROVIDER="wsl2"
  fi
}

detect_pkg() {
  if   have apt-get; then PKG="apt";    PKG_INSTALL="sudo apt-get install -y"
  elif have dnf;     then PKG="dnf";    PKG_INSTALL="sudo dnf install -y"
  elif have yum;     then PKG="yum";    PKG_INSTALL="sudo yum install -y"
  elif have pacman;  then PKG="pacman"; PKG_INSTALL="sudo pacman -S --noconfirm"
  elif have zypper;  then PKG="zypper"; PKG_INSTALL="sudo zypper install -y"
  elif have apk;     then PKG="apk";    PKG_INSTALL="sudo apk add"
  else PKG=""; PKG_INSTALL=""; fi
}

# Returns version string or empty
ver() { "$@" 2>/dev/null | head -n1; }

cpu_cores()  { nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo "?"; }
mem_total()  { awk '/MemTotal/{printf "%.1f GiB", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo "?"; }
disk_free()  { df -h "$1" 2>/dev/null | awk 'NR==2{print $4" free of "$2}'; }
kvm_ok()     { [ -e /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ]; }

report_tool() {
  # usage: report_tool LABEL CMD [ARGS...]   (CMD = probe binary, rest = version args)
  local label="$1"; shift
  local bin="$1"
  if have "$bin"; then
    local path; path="$(command -v "$bin")"
    local v; v="$("$@" 2>&1 | head -n1)"
    printf '   %sok%s   %-16s %s%s%s  %s%s%s\n' "$GREEN" "$RESET" "$label" "$BOLD" "$v" "$RESET" "$DIM" "$path" "$RESET"
    return 0
  fi
  printf '   %smiss%s %-16s %snot found%s\n' "$RED" "$RESET" "$label" "$DIM" "$RESET"
  return 1
}

print_report() {
  detect_distro; detect_pkg
  hr() { printf '%s\n' "------------------------------------------------------------"; }
  hr
  info "Host & device report"
  hr
  printf '   %-16s %s\n' "OS"        "$HOST_DISTRO ($HOST_OS/$HOST_ARCH)"
  printf '   %-16s %s\n' "Kernel"    "$HOST_KERNEL"
  printf '   %-16s %s\n' "Provider"  "$PROVIDER"
  printf '   %-16s %s\n' "Pkg manager" "${PKG:-none detected}"
  printf '   %-16s %s\n' "CPU cores" "$(cpu_cores)"
  printf '   %-16s %s\n' "Memory"    "$(mem_total)"
  printf '   %-16s %s\n' "Disk"      "$(disk_free "$HOME")"
  if kvm_ok; then
    printf '   %-16s %savailable%s — Windows/Linux VM labs supported\n' "KVM" "$GREEN" "$RESET"
  elif [ -e /dev/kvm ]; then
    printf '   %-16s %spresent, no access%s — add your user to the kvm group\n' "KVM" "$YELLOW" "$RESET"
  else
    printf '   %-16s %sunavailable%s — VM labs (win/linux) need nested virt\n' "KVM" "$YELLOW" "$RESET"
  fi
  hr
  info "Host tools"
  hr
  report_tool "git"       git     --version
  report_tool "python3"   python3 --version
  if have pip3; then report_tool "pip" pip3 --version
  else report_tool "pip" pip --version; fi
  report_tool "docker"    docker  --version
  if have docker; then
    if docker compose version >/dev/null 2>&1; then
      ok "compose          $(docker compose version 2>/dev/null | head -n1)"
    elif have docker-compose; then
      report_tool "compose" docker-compose --version
    else
      miss "compose          not found"
    fi
  fi
  report_tool "adb"       adb     --version
  report_tool "java"      java    -version
  report_tool "node"      node    --version
  hr
}

# --------------------------------------------------------------------------- #
# Prerequisite install
# --------------------------------------------------------------------------- #
PY_VENV_PKG=""
ensure_prereqs() {
  detect_pkg
  [ -n "$PKG" ] || { warn "no supported package manager found; install git + python3 + venv manually"; return 0; }

  # Package names differ per manager: Arch/Alpine/openSUSE ship the python3
  # interpreter in a package named `python`, and bundle venv with it.
  local py_pkg="python3"
  case "$PKG" in
    apt)     PY_VENV_PKG="python3-venv python3-pip" ;;
    dnf|yum) PY_VENV_PKG="python3-pip" ;;
    pacman|apk|zypper) py_pkg="python"; PY_VENV_PKG="" ;;
    *) PY_VENV_PKG="" ;;
  esac

  local want=()
  have git                      || want+=("git")
  have python3 || have python   || want+=("$py_pkg")
  have curl                     || want+=("curl")

  # python venv module check (whichever interpreter exists)
  local py; py="$(command -v python3 || command -v python || true)"
  if [ -n "$py" ] && ! "$py" -m venv --help >/dev/null 2>&1; then
    [ -n "$PY_VENV_PKG" ] && want+=($PY_VENV_PKG)
  fi

  if [ "${#want[@]}" -eq 0 ]; then
    ok "all core prerequisites already present"
    return 0
  fi

  step "installing: ${want[*]}  (via $PKG)"
  if [ "$PKG" = "apt" ]; then sudo apt-get update -y >/dev/null 2>&1 || true; fi
  # shellcheck disable=SC2086
  $PKG_INSTALL ${want[*]} || warn "prerequisite install reported errors; continuing"
}

# --------------------------------------------------------------------------- #
# Fetch / update the checkout
# --------------------------------------------------------------------------- #
REPO_ROOT=""
CLONED=0
locate_or_clone() {
  # If we are already inside an os-lab checkout, prefer it.
  local here
  here="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$here" ] && [ -f "$here/labctl" ] && [ -d "$here/android-lab" ]; then
    REPO_ROOT="$here"
    step "using existing checkout: $REPO_ROOT"
  elif [ -d "$OSLAB_DIR/.git" ]; then
    REPO_ROOT="$OSLAB_DIR"
    step "found checkout: $REPO_ROOT"
  else
    step "cloning $OSLAB_REPO → $OSLAB_DIR"
    have git || die "git is required to clone (run without --no-install, or install git)"
    git clone --branch "$OSLAB_BRANCH" "$OSLAB_REPO" "$OSLAB_DIR" \
      || die "git clone failed"
    REPO_ROOT="$OSLAB_DIR"
    CLONED=1
    return 0
  fi

  # Update only a freshly-cloned checkout, or when --update is explicit.
  # Never switch branches: fast-forward whatever branch the user is on, so a
  # developer's working branch is left untouched.
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

# --------------------------------------------------------------------------- #
# Python virtualenv
# --------------------------------------------------------------------------- #
VENV_DIR=""
provision_venv() {
  VENV_DIR="$REPO_ROOT/.venv"
  local req="$REPO_ROOT/android-lab/lab/requirements.txt"

  local py; py="$(command -v python3 || command -v python || true)"
  [ -n "$py" ] || die "no python interpreter found; install python3 (run without --no-install)"
  if [ ! -d "$VENV_DIR" ]; then
    step "creating virtualenv: $VENV_DIR"
    "$py" -m venv "$VENV_DIR" || die "failed to create virtualenv"
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

# --------------------------------------------------------------------------- #
# Launch the web console (PWA UI)
# --------------------------------------------------------------------------- #
open_browser() {
  local url="$1"
  if   have xdg-open; then xdg-open "$url" >/dev/null 2>&1 &
  elif grep -qi wsl /proc/version 2>/dev/null && have powershell.exe; then
    powershell.exe -NoProfile Start-Process "$url" >/dev/null 2>&1 &
  fi
}

launch_ui() {
  local orch="$REPO_ROOT/android-lab/lab/orchestrator.py"
  local url="http://127.0.0.1:$OSLAB_PORT"
  [ -f "$orch" ] || die "web console entrypoint missing: $orch"
  info "Launching os-lab web console → $url"
  step "press Ctrl+C to stop"
  open_browser "$url"
  # Foreground so Ctrl+C stops it cleanly.
  exec python "$orch" ui --port "$OSLAB_PORT"
}

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
banner
print_report

if [ "$REPORT_ONLY" -eq 1 ]; then
  info "report-only: no changes made"
  exit 0
fi

[ "$DO_INSTALL" -eq 1 ] && { info "Checking prerequisites"; ensure_prereqs; }
info "Fetching os-lab"
locate_or_clone
info "Provisioning Python environment"
provision_venv
info "Preparing the dashboard"
build_dashboard

if [ "$DO_RUN" -eq 1 ]; then
  launch_ui
else
  hr() { printf '%s\n' "------------------------------------------------------------"; }
  hr
  ok "setup complete — checkout at $REPO_ROOT"
  printf '   start the console later with:\n'
  printf '     %scd %s && . .venv/bin/activate && python android-lab/lab/orchestrator.py ui --port %s%s\n' \
    "$DIM" "$REPO_ROOT" "$OSLAB_PORT" "$RESET"
fi

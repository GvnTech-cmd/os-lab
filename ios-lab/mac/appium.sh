#!/usr/bin/env bash
# Start, stop or inspect the shared Appium server (XCUITest for the iOS Lab, mac2 for the macOS Lab).
#
#   appium.sh install       install Node (Homebrew), Appium and the XCUITest/mac2 drivers for this user only
#   appium.sh start|stop|status
set -euo pipefail

. "$(dirname "$0")/lib.sh"
require_macos

ACTION="${1:-status}"
PID_FILE="$MAC_DIR/.appium.pid"
mkdir -p "$LAB_DIR/artifacts"
case "$APPIUM_LOG" in
  /*) LOG="$APPIUM_LOG" ;;
  *) LOG="$LAB_DIR/$APPIUM_LOG" ;;
esac
mkdir -p "$(dirname "$LOG")"

# Appium installed by `appium.sh install` lives in the user's folder, so no administrator rights or
# global npm directory are needed. A copy already on PATH keeps working.
APPIUM_PREFIX="${OSLAB_APPIUM_HOME:-$HOME/.oslab/appium}"
MANAGED_BIN="$APPIUM_PREFIX/node_modules/.bin/appium"
appium_bin() {
  if [ -x "$MANAGED_BIN" ]; then echo "$MANAGED_BIN"; else command -v appium 2>/dev/null || true; fi
}
if [ -x "$MANAGED_BIN" ]; then export APPIUM_HOME="$APPIUM_PREFIX/home"; fi

# One machine-readable line per step; the dashboard turns these into a progress bar.
progress() { printf '##PROGRESS %s/%s %s\n' "$1" "$2" "$3"; say "$3"; }

node_ok() {
  command -v node >/dev/null 2>&1 && node -e '
    const [a, b] = process.versions.node.split(".").map(Number);
    process.exit(a > 22 || (a === 22 && b >= 12) || (a === 20 && b >= 19) ? 0 : 1)'
}

running() {
  [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

case "$ACTION" in
  install)
    TOTAL=5
    progress 1 $TOTAL "Checking Node.js"
    if ! node_ok; then
      command -v brew >/dev/null 2>&1 || die "Node.js 20.19+ or 22.12+ is required and Homebrew is not installed. Install Node from https://nodejs.org or Homebrew from https://brew.sh, then try again."
      progress 2 $TOTAL "Installing Node.js with Homebrew"
      brew install node
      hash -r
      node_ok || die "Node.js is still older than 20.19 after the Homebrew install; run: brew upgrade node"
    else
      progress 2 $TOTAL "Node.js $(node --version) is ready"
    fi
    progress 3 $TOTAL "Installing Appium into $APPIUM_PREFIX"
    mkdir -p "$APPIUM_PREFIX/home"
    npm install --prefix "$APPIUM_PREFIX" --no-audit --no-fund appium
    export APPIUM_HOME="$APPIUM_PREFIX/home"
    progress 4 $TOTAL "Installing the XCUITest and mac2 drivers"
    for driver in xcuitest mac2; do
      if "$MANAGED_BIN" driver list --installed 2>&1 | grep -q "$driver"; then
        say "$driver driver already installed"
      else
        "$MANAGED_BIN" driver install "$driver"
      fi
    done
    progress 5 $TOTAL "Checking the install"
    "$MANAGED_BIN" --version
    "$MANAGED_BIN" driver list --installed 2>&1 | grep -q xcuitest || die "the XCUITest driver is not installed"
    "$MANAGED_BIN" driver list --installed 2>&1 | grep -q mac2 || die "the mac2 driver is not installed"
    say "Appium is ready. Start it from the iOS or macOS Lab page (Start Appium)."
    ;;
  start)
    # The server itself needs no Xcode: the iOS Lab gates on Xcode before offering simulator
    # actions, and the macOS Lab's mac2 sessions only need the driver and Accessibility.
    APPIUM="$(appium_bin)"
    [ -n "$APPIUM" ] || die "Appium is not installed; use Install Appium in the iOS or macOS Lab page"
    if running; then
      say "Appium already running (pid $(cat "$PID_FILE")) on ${APPIUM_HOST}:${APPIUM_PORT}"
      exit 0
    fi
    say "starting Appium on ${APPIUM_HOST}:${APPIUM_PORT}"
    nohup "$APPIUM" --address "$APPIUM_HOST" --port "$APPIUM_PORT" >"$LOG" 2>&1 &
    echo $! > "$PID_FILE"
    for ((i = 0; i < 30; i++)); do
      if curl -fsS --max-time 2 "http://${APPIUM_HOST}:${APPIUM_PORT}/status" >/dev/null 2>&1; then
        say "Appium ready (pid $(cat "$PID_FILE"), log $LOG)"
        exit 0
      fi
      sleep 1
    done
    tail -20 "$LOG" >&2 || true
    die "Appium did not become ready; see $LOG"
    ;;
  stop)
    if running; then
      PID="$(cat "$PID_FILE")"
      kill "$PID" 2>/dev/null || true
      for ((i = 0; i < 15; i++)); do
        kill -0 "$PID" 2>/dev/null || break
        sleep 1
      done
      kill -9 "$PID" 2>/dev/null || true
      rm -f "$PID_FILE"
      say "Appium stopped"
    else
      rm -f "$PID_FILE"
      say "Appium is not running"
    fi
    ;;
  status)
    if running; then
      say "Appium running (pid $(cat "$PID_FILE")) on ${APPIUM_HOST}:${APPIUM_PORT}"
      curl -fsS --max-time 2 "http://${APPIUM_HOST}:${APPIUM_PORT}/status" || true
      echo
    else
      say "Appium is not running"
    fi
    ;;
  *)
    die "usage: $0 install|start|stop|status"
    ;;
esac

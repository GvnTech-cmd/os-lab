#!/usr/bin/env bash
# Status, doctor and one Appium mac2 smoke session for macOS applications on this Mac.
# The macOS Lab drives installed applications (Appium mac2); the iOS Simulator lives
# in the iOS Lab through run-simulator.sh.
#
#   macos-app.sh status|doctor|smoke|repl
set -uo pipefail

. "$(dirname "$0")/lib.sh"
require_macos

ACTION="${1:-status}"

# Appium installed by `appium.sh install` lives in the user's folder, so no administrator
# rights or global npm directory are needed. A copy already on PATH keeps working.
APPIUM_PREFIX="${OSLAB_APPIUM_HOME:-$HOME/.oslab/appium}"
MANAGED_BIN="$APPIUM_PREFIX/node_modules/.bin/appium"
appium_bin() {
  if [ -x "$MANAGED_BIN" ]; then echo "$MANAGED_BIN"; else command -v appium 2>/dev/null || true; fi
}

ok()   { printf '  [ok]   %s\n' "$*"; }
warn() { printf '  [warn] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=1; }
progress() { printf '##PROGRESS %s/%s %s\n' "$1" "$2" "$3"; say "$3"; }

appium_state() {
  if curl -fsS --max-time 2 "http://${APPIUM_HOST}:${APPIUM_PORT}/status" >/dev/null 2>&1; then
    ok "Appium is listening on ${APPIUM_HOST}:${APPIUM_PORT}"
  else
    warn "Appium is not running on ${APPIUM_HOST}:${APPIUM_PORT} (make mac-appium)"
  fi
}

mac2_driver_state() {
  APPIUM="$(appium_bin)"
  [ -n "$APPIUM" ] || { warn "appium not found (Install Appium in the macOS Lab page)"; return; }
  if [ -x "$MANAGED_BIN" ]; then export APPIUM_HOME="$APPIUM_PREFIX/home"; fi
  if "$APPIUM" driver list --installed 2>/dev/null | grep -q mac2; then
    ok "mac2 driver installed"
  else
    warn "mac2 driver missing (appium driver install mac2, or Install Appium again)"
  fi
}

case "$ACTION" in
  status)
    echo "macos-lab (macOS applications)"
    echo "config      $CONFIG"
    echo "macos       $(sw_vers -productName) $(sw_vers -productVersion) ($(uname -m))"
    echo "appium"
    if command -v appium >/dev/null 2>&1; then
      echo "  $(appium --version 2>/dev/null || echo present)"
    else
      echo "  not installed"
    fi
    if curl -fsS --max-time 2 "http://${APPIUM_HOST}:${APPIUM_PORT}/status" >/dev/null 2>&1; then
      echo "  http://${APPIUM_HOST}:${APPIUM_PORT} ready"
    else
      echo "  not running"
    fi
    echo "mac2 driver"
    if command -v appium >/dev/null 2>&1 && appium driver list --installed 2>/dev/null | grep -q mac2; then
      echo "  installed"
    else
      echo "  missing"
    fi
    echo "resources"
    echo "  disk free $(df -h "$LAB_DIR" | awk 'NR==2 {print $4}')"
    echo "  memory    $(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 )) GB"
    ;;
  doctor)
    FAIL=0
    say "host"
    ok "$(sw_vers -productName) $(sw_vers -productVersion) ($(uname -m))"
    ok "cpu: $(sysctl -n hw.ncpu) cores"
    MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
    if [ "$MEM_GB" -lt 8 ]; then warn "memory: ${MEM_GB} GB (8 GB+ recommended for mac2 sessions)"; else ok "memory: ${MEM_GB} GB"; fi
    ok "disk free: $(df -h "$LAB_DIR" | awk 'NR==2 {print $4}')"

    say "appium"
    if command -v node >/dev/null 2>&1; then ok "node: $(node --version)"; else warn "node not found (brew install node)"; fi
    if command -v appium >/dev/null 2>&1; then
      ok "appium: $(appium --version 2>/dev/null || echo present)"
    else
      warn "appium not found (Install Appium in the macOS Lab page)"
    fi
    mac2_driver_state
    appium_state

    say "permissions"
    AX_PROBE="$(osascript -e 'tell application "System Events" to get position of window 1 of (first application process whose frontmost is true)' 2>&1 || true)"
    if [ -n "$AX_PROBE" ] && [ "${AX_PROBE#*assistive}" = "$AX_PROBE" ]; then
      ok "Accessibility: granted (element reads work)"
    else
      warn "Accessibility: not granted for the console — mac2 sessions, the REPL and the app mirror cannot read or click (System Settings > Privacy & Security > Accessibility)"
    fi
    warn "Screen Recording: grant it to the console if the app mirror stays empty or captures fail (System Settings > Privacy & Security > Screen Recording)"
    ok "config file: $CONFIG"

    echo
    if [ "$FAIL" -eq 0 ]; then echo "macOS Lab ready. Next: make mac-appium && make mac-app-smoke"; else echo "macOS Lab has failures."; fi
    exit "$FAIL"
    ;;
  smoke)
    TOTAL=4
    progress 1 $TOTAL "Checking the automation stack"
    APPIUM="$(appium_bin)"
    [ -n "$APPIUM" ] || die "Appium is not installed; use Install Appium in the macOS Lab page"
    if [ -x "$MANAGED_BIN" ]; then export APPIUM_HOME="$APPIUM_PREFIX/home"; fi
    "$APPIUM" driver list --installed 2>/dev/null | grep -q mac2 \
      || die "the Appium mac2 driver is not installed; run Install Appium again"
    curl -fsS --max-time 2 "http://${APPIUM_HOST}:${APPIUM_PORT}/status" >/dev/null 2>&1 \
      || die "Appium is not running on ${APPIUM_HOST}:${APPIUM_PORT}; start it first (Start Appium)"

    progress 2 $TOTAL "Preparing the mac2 session for Finder"
    CAPS="$(python3 -c 'import json; print(json.dumps({"capabilities": {"alwaysMatch": {
      "platformName": "mac", "appium:automationName": "mac2", "appium:bundleId": "com.apple.finder"}}}))')"

    progress 3 $TOTAL "Creating the mac2 session (grant Accessibility permission if macOS asks)"
    RESPONSE="$(curl -fsS --max-time 300 -X POST "http://${APPIUM_HOST}:${APPIUM_PORT}/session" \
      -H "Content-Type: application/json" -d "$CAPS")" \
      || die "the mac2 session failed; see the Appium log (${APPIUM_LOG}) and grant Accessibility permission if macOS asked"
    SESSION_ID="$(printf '%s' "$RESPONSE" | python3 -c 'import json, sys; print(json.load(sys.stdin)["value"]["sessionId"])' 2>/dev/null || true)"
    [ -n "$SESSION_ID" ] || die "Appium did not return a session id; see the Appium log (${APPIUM_LOG})"

    progress 4 $TOTAL "Closing the session"
    curl -fsS --max-time 30 -X DELETE "http://${APPIUM_HOST}:${APPIUM_PORT}/session/$SESSION_ID" >/dev/null 2>&1 || true
    say "macOS app smoke passed: mac2 session $SESSION_ID activated Finder"
    ;;
  repl)
    # Interactive mac2 REPL (macos-repl.mjs): a local operator tool with its own terminal
    # session. Never a console job — stdin does not survive the background job runner, and
    # the web console keeps its preview → confirm model for everything it runs.
    command -v node >/dev/null 2>&1 || die "node is required for the REPL (brew install node)"
    APPIUM="$(appium_bin)"
    [ -n "$APPIUM" ] || die "Appium is not installed; use Install Appium in the macOS Lab page"
    if [ -x "$MANAGED_BIN" ]; then export APPIUM_HOME="$APPIUM_PREFIX/home"; fi
    "$APPIUM" driver list --installed 2>/dev/null | grep -q mac2 \
      || die "the Appium mac2 driver is not installed; run Install Appium again"
    curl -fsS --max-time 2 "http://${APPIUM_HOST}:${APPIUM_PORT}/status" >/dev/null 2>&1 \
      || die "Appium is not running on ${APPIUM_HOST}:${APPIUM_PORT}; start it first (make mac-appium)"
    mkdir -p "$LAB_DIR/artifacts"
    exec node "$MAC_DIR/macos-repl.mjs" "http://${APPIUM_HOST}:${APPIUM_PORT}" "${MACOS_APP:-com.apple.finder}" "$LAB_DIR/artifacts"
    ;;
  click)
    # One real click on this Mac: bring the owning app forward, then post the event at the
    # point. Runs as a previewed lab action (macos-click) and, while control mode is armed,
    # directly from the app mirror. Needs Accessibility permission for the console.
    PID="${1:-}"; X="${2:-}"; Y="${3:-}"
    case "$PID$X$Y" in ''|*[!0-9]*) die "usage: $0 click <pid> <x> <y> (integers)" ;; esac
    osascript -e "tell application \"System Events\" to set frontmost of (first application process whose unix id is $PID) to true" >/dev/null 2>&1 \
      || warn "could not bring pid $PID forward; the click may land elsewhere"
    sleep 0.4
    osascript -l JavaScript -e '
      ObjC.import("CoreGraphics");
      function run(argv) {
        const p = $.CGPointMake(parseFloat(argv[0]), parseFloat(argv[1]));
        $.CGEventPost($.kCGHIDEventTap, $.CGEventCreateMouseEvent($(), $.kCGEventMouseMoved, p, $.kCGMouseButtonLeft));
        $.CGEventPost($.kCGHIDEventTap, $.CGEventCreateMouseEvent($(), $.kCGEventLeftMouseDown, p, $.kCGMouseButtonLeft));
        $.CGEventPost($.kCGHIDEventTap, $.CGEventCreateMouseEvent($(), $.kCGEventLeftMouseUp, p, $.kCGMouseButtonLeft));
        return "clicked " + argv[0] + "," + argv[1];
      }
    ' "$X" "$Y" || die "the click could not be posted; grant Accessibility permission to the console"
    ;;
  *)
    die "usage: $0 status|doctor|smoke|repl|click"
    ;;
esac

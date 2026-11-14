#!/usr/bin/env bash
# port-check — is a lab's host port free or already taken? (read-only)
#
# Fills a gap: the single most common lab start failure is "port is already
# allocated" (WEB_PORT 8006 / SSH_PORT 2222 clash with a stray container or a
# previous run). This checks TCP ports on 127.0.0.1 *before* `make up`, using
# only bash's /dev/tcp — no nc/lsof/ss required, so it works the same on macOS
# and Linux. It opens and immediately closes a probe connection; it never sends
# data and never listens.
#
# Usage:
#   scripts/bonus/port-check.sh                 # reads WEB_PORT/SSH_PORT from ./.env(.example)
#   scripts/bonus/port-check.sh --lab ../win-lab
#   scripts/bonus/port-check.sh 8006 2222 5900  # explicit ports
#   scripts/bonus/port-check.sh --host 127.0.0.1 8080
#
# Exit status: 0 = every checked port is free, 1 = at least one is in use,
# 2 = usage error.
set -euo pipefail

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; BOLD=""; RESET=""
fi

die() { printf '%serror:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 2; }

HOST="127.0.0.1"
LAB_DIR=""
PORTS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:-}"; shift 2 || die "--host needs a value" ;;
    --lab)  LAB_DIR="${2:-}"; shift 2 || die "--lab needs a directory" ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) case "$1" in
         *[!0-9]*) die "not a port number: $1" ;;
         *) [ "$1" -ge 1 ] && [ "$1" -le 65535 ] || die "port out of range: $1"
            PORTS="$PORTS $1" ;;
       esac
       shift ;;
  esac
done

# No explicit ports: read WEB_PORT / SSH_PORT from the lab's .env or .env.example.
if [ -z "${PORTS// /}" ]; then
  src=""
  for cand in "${LAB_DIR:+$LAB_DIR/}.env" "${LAB_DIR:+$LAB_DIR/}.env.example"; do
    [ -f "$cand" ] && { src="$cand"; break; }
  done
  [ -n "$src" ] || die "no ports given and no .env/.env.example found${LAB_DIR:+ in $LAB_DIR}"
  for key in WEB_PORT SSH_PORT; do
    val="$(sed -e 's/\r$//' "$src" \
            | grep -E "^[[:space:]]*(export[[:space:]]+)?$key=" \
            | tail -n1 | sed -E "s/^[^=]*=//; s/[[:space:]].*$//")"
    case "$val" in ''|*[!0-9]*) ;; *) PORTS="$PORTS $val" ;; esac
  done
  [ -n "${PORTS// /}" ] || die "found $src but no numeric WEB_PORT/SSH_PORT in it"
  printf '%sport-check%s  %s  ports from %s\n' "$BOLD" "$RESET" "$HOST" "$src"
else
  printf '%sport-check%s  %s\n' "$BOLD" "$RESET" "$HOST"
fi

# Open a TCP connection with a short timeout; 0 = something is listening.
probe() {
  local host="$1" port="$2"
  if command -v timeout >/dev/null 2>&1; then
    timeout 2 bash -c "exec 3<>/dev/tcp/$host/$port" 2>/dev/null && { exec 3>&- 3<&- 2>/dev/null; return 0; }
    return 1
  fi
  ( exec 3<>/dev/tcp/"$host"/"$port" ) 2>/dev/null && return 0 || return 1
}

in_use=0
for p in $PORTS; do
  if probe "$HOST" "$p"; then
    printf '  %s[in use]%s %s/tcp — a process is already listening\n' "$RED" "$RESET" "$p"
    in_use=$((in_use + 1))
  else
    printf '  %s[free]%s   %s/tcp\n' "$GREEN" "$RESET" "$p"
  fi
done

if [ "$in_use" -eq 0 ]; then
  printf '%s[ok]%s all checked ports are free\n' "$GREEN" "$RESET"
  exit 0
fi
printf '%s[fail]%s %s port(s) in use — stop the owner or change the port in .env\n' "$RED" "$RESET" "$in_use"
exit 1

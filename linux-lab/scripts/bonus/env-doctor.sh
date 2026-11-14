#!/usr/bin/env bash
# env-doctor — validate a lab .env against its .env.example (read-only).
#
# Fills a gap: labs ship a .env.example but nothing checks that a copied .env
# still matches it. This flags missing keys, empty values, unknown/extra keys
# and duplicate keys before `docker compose` or the lab scripts read a broken
# .env and fail with a confusing error.
#
# Usage:
#   scripts/bonus/env-doctor.sh                 # checks ./.env against ./.env.example
#   scripts/bonus/env-doctor.sh --lab ../win-lab
#   scripts/bonus/env-doctor.sh --env .env --example .env.example
#   scripts/bonus/env-doctor.sh --json
#
# Read-only: it never writes, exports or prints a value, only key names.
# Exit status: 0 = clean, 1 = problems found, 2 = usage/IO error.
set -euo pipefail

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BOLD=""; RESET=""
fi

LAB_DIR=""
ENV_FILE=""
EXAMPLE_FILE=""
JSON=0

die() { printf '%serror:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --lab)     LAB_DIR="${2:-}"; shift 2 || die "--lab needs a directory" ;;
    --env)     ENV_FILE="${2:-}"; shift 2 || die "--env needs a path" ;;
    --example) EXAMPLE_FILE="${2:-}"; shift 2 || die "--example needs a path" ;;
    --json)    JSON=1; shift ;;
    -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

if [ -n "$LAB_DIR" ]; then
  [ -d "$LAB_DIR" ] || die "lab directory not found: $LAB_DIR"
  : "${ENV_FILE:=$LAB_DIR/.env}"
  : "${EXAMPLE_FILE:=$LAB_DIR/.env.example}"
else
  : "${ENV_FILE:=.env}"
  : "${EXAMPLE_FILE:=.env.example}"
fi

[ -f "$EXAMPLE_FILE" ] || die "example file not found: $EXAMPLE_FILE"
[ -f "$ENV_FILE" ]     || die "env file not found: $ENV_FILE (copy it: cp '$EXAMPLE_FILE' '$ENV_FILE')"

# Extract KEY names from a dotenv file: lines like KEY=... , ignoring comments,
# blanks and a leading `export `. Values are never captured.
keys_of() {
  sed -e 's/\r$//' "$1" \
    | grep -E '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=' \
    | sed -E 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/'
}

# Keys whose value is empty (KEY= with nothing after, ignoring trailing spaces).
empty_keys_of() {
  sed -e 's/\r$//' "$1" \
    | grep -E '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=[[:space:]]*$' \
    | sed -E 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/' || true
}

EXAMPLE_KEYS="$(keys_of "$EXAMPLE_FILE" | sort -u)"
ENV_KEYS_RAW="$(keys_of "$ENV_FILE")"
ENV_KEYS="$(printf '%s\n' "$ENV_KEYS_RAW" | sort -u)"

MISSING="$(comm -23 <(printf '%s\n' "$EXAMPLE_KEYS") <(printf '%s\n' "$ENV_KEYS") | grep -v '^$' || true)"
UNKNOWN="$(comm -13 <(printf '%s\n' "$EXAMPLE_KEYS") <(printf '%s\n' "$ENV_KEYS") | grep -v '^$' || true)"
DUPES="$(printf '%s\n' "$ENV_KEYS_RAW" | sort | uniq -d | grep -v '^$' || true)"
EMPTY="$(empty_keys_of "$ENV_FILE" | sort -u | grep -v '^$' || true)"

count() { [ -z "$1" ] && echo 0 || printf '%s\n' "$1" | grep -c '^'; }
n_missing=$(count "$MISSING"); n_unknown=$(count "$UNKNOWN")
n_dupes=$(count "$DUPES");     n_empty=$(count "$EMPTY")
problems=$((n_missing + n_dupes + n_empty))

if [ "$JSON" = "1" ]; then
  csv() { printf '%s\n' "$1" | grep -v '^$' | awk 'BEGIN{ORS=""} {printf "%s\"%s\"", (NR>1?",":""), $0}'; }
  printf '{"env":"%s","example":"%s",' "$ENV_FILE" "$EXAMPLE_FILE"
  printf '"missing":[%s],' "$(csv "$MISSING")"
  printf '"empty":[%s],'   "$(csv "$EMPTY")"
  printf '"unknown":[%s],' "$(csv "$UNKNOWN")"
  printf '"duplicate":[%s],' "$(csv "$DUPES")"
  printf '"ok":%s}\n' "$([ "$problems" -eq 0 ] && echo true || echo false)"
  [ "$problems" -eq 0 ] && exit 0 || exit 1
fi

printf '%senv-doctor%s  %s  (against %s)\n' "$BOLD" "$RESET" "$ENV_FILE" "$EXAMPLE_FILE"
show() { # label color list
  local label="$1" color="$2" list="$3"
  if [ -n "$list" ]; then
    printf '  %s%s%s\n' "$color" "$label" "$RESET"
    printf '%s\n' "$list" | grep -v '^$' | sed 's/^/    - /'
  fi
}
show "missing (in example, not in .env):" "$RED" "$MISSING"
show "empty value (KEY= with nothing set):" "$RED" "$EMPTY"
show "duplicate keys (last one wins):" "$RED" "$DUPES"
show "unknown (in .env, not in example):" "$YELLOW" "$UNKNOWN"

if [ "$problems" -eq 0 ]; then
  if [ -n "$UNKNOWN" ]; then
    printf '%s[ok]%s required keys present; %s extra key(s) above are only a warning\n' "$GREEN" "$RESET" "$n_unknown"
  else
    printf '%s[ok]%s .env matches .env.example\n' "$GREEN" "$RESET"
  fi
  exit 0
fi
printf '%s[fail]%s %s problem(s): %s missing, %s empty, %s duplicate\n' \
  "$RED" "$RESET" "$problems" "$n_missing" "$n_empty" "$n_dupes"
exit 1

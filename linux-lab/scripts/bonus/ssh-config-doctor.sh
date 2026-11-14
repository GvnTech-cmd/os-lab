#!/usr/bin/env bash
# ssh-config-doctor — summarise and sanity-check ~/.ssh/config (read-only).
#
# Fills a gap: the lab uses Remote-SSH heavily (OS-02/OS-17/OS-20) and students
# routinely break their ~/.ssh/config — missing IdentityFile, a key with loose
# permissions that makes ssh ignore it, or a Host with no HostName. This prints
# each Host block's effective settings and flags those faults. It never
# connects anywhere and never prints a key's contents.
#
# Usage:
#   scripts/bonus/ssh-config-doctor.sh
#   scripts/bonus/ssh-config-doctor.sh --file /path/to/ssh_config
#   scripts/bonus/ssh-config-doctor.sh --host lab    # only the "lab" block
#
# Exit status: 0 = no problems, 1 = at least one problem, 2 = usage/IO error.
set -euo pipefail

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BOLD=""; RESET=""
fi

die() { printf '%serror:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 2; }

CONFIG="${HOME}/.ssh/config"
ONLY_HOST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --file) CONFIG="${2:-}"; shift 2 || die "--file needs a path" ;;
    --host) ONLY_HOST="${2:-}"; shift 2 || die "--host needs a name" ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[ -f "$CONFIG" ] || die "ssh config not found: $CONFIG"

problems=0
hosts=0

# Expand a leading ~ in an IdentityFile path for the existence check.
# shellcheck disable=SC2088  # the "~/" here is a literal glob pattern, not an expansion
expand() { case "$1" in "~/"*) printf '%s/%s' "$HOME" "${1#~/}" ;; *) printf '%s' "$1" ;; esac; }

# Mode check without stat's incompatible flags across macOS/Linux: a key must
# not be group/other readable. We test with a tiny perl-free approach via ls.
key_too_open() {
  local f="$1" perms
  perms="$(ls -l "$f" 2>/dev/null | awk '{print $1}')" || return 1
  # perms like -rw------- ; chars 5-10 are group+other. Any non '-' is too open.
  case "${perms:4:6}" in
    "------") return 1 ;;  # fine
    *) return 0 ;;          # too open
  esac
}

cur=""; hostname=""; user=""; port=""; identity=""
flush() {
  [ -z "$cur" ] && return 0
  if [ -n "$ONLY_HOST" ] && [ "$cur" != "$ONLY_HOST" ]; then
    cur=""; hostname=""; user=""; port=""; identity=""; return 0
  fi
  case "$cur" in *[*?]*) is_pattern=1 ;; *) is_pattern=0 ;; esac
  hosts=$((hosts + 1))
  printf '%s%s%s\n' "$BOLD" "Host $cur" "$RESET"
  printf '    HostName     %s\n' "${hostname:-(none)}"
  printf '    User         %s\n' "${user:-(default)}"
  printf '    Port         %s\n' "${port:-22}"
  printf '    IdentityFile %s\n' "${identity:-(default)}"

  if [ -z "$hostname" ] && [ "$is_pattern" = "0" ]; then
    printf '    %s! no HostName — ssh will try to resolve "%s" literally%s\n' "$RED" "$cur" "$RESET"
    problems=$((problems + 1))
  fi
  if [ -n "$identity" ]; then
    local path; path="$(expand "$identity")"
    if [ ! -f "$path" ]; then
      printf '    %s! IdentityFile missing on disk: %s%s\n' "$RED" "$path" "$RESET"
      problems=$((problems + 1))
    elif key_too_open "$path"; then
      printf '    %s! IdentityFile is group/other readable — ssh may ignore it; run: chmod 600 %s%s\n' "$RED" "$path" "$RESET"
      problems=$((problems + 1))
    fi
  fi
  cur=""; hostname=""; user=""; port=""; identity=""
}

# Parse: Host lines start a block; keys are case-insensitive, space or = sep.
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"
  trimmed="$(printf '%s' "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  case "$trimmed" in ''|'#'*) continue ;; esac
  key="$(printf '%s' "$trimmed" | sed -E 's/[[:space:]=].*$//' | tr 'A-Z' 'a-z')"
  val="$(printf '%s' "$trimmed" | sed -E 's/^[^[:space:]=]+[[:space:]=]+//')"
  case "$key" in
    host)         flush; cur="$(printf '%s' "$val" | awk '{print $1}')" ;;
    hostname)     hostname="$val" ;;
    user)         user="$val" ;;
    port)         port="$val" ;;
    identityfile) identity="$val" ;;
  esac
done < "$CONFIG"
flush

if [ "$hosts" -eq 0 ]; then
  if [ -n "$ONLY_HOST" ]; then die "no Host block named '$ONLY_HOST' in $CONFIG"; fi
  printf '%s[ok]%s %s has no Host blocks\n' "$YELLOW" "$RESET" "$CONFIG"; exit 0
fi
if [ "$problems" -eq 0 ]; then
  printf '%s[ok]%s %s host block(s), no problems\n' "$GREEN" "$RESET" "$hosts"; exit 0
fi
printf '%s[fail]%s %s problem(s) across %s host block(s)\n' "$RED" "$RESET" "$problems" "$hosts"
exit 1

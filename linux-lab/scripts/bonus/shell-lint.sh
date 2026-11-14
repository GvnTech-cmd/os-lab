#!/usr/bin/env bash
# shell-lint — syntax-check the shell scripts you are about to submit (read-only).
#
# Fills a gap: CONTRIBUTING tells contributors to run the full
# scripts/run-tests.sh before a PR, but there is no quick, scoped way to check
# just the scripts you touched. This runs `bash -n` on every *.sh under a path
# (the same gate run-tests.sh stage 3 applies repo-wide) and, when shellcheck is
# installed, adds its advisory findings without failing on them.
#
# Usage:
#   scripts/bonus/shell-lint.sh                 # lints ./ (the current dir)
#   scripts/bonus/shell-lint.sh linux-lab/scripts
#   scripts/bonus/shell-lint.sh path/to/one.sh
#
# Exit status: 0 = all parse, 1 = a syntax error, 2 = usage error.
set -euo pipefail

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BOLD=""; RESET=""
fi

die() { printf '%serror:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 2; }

TARGET="."
case "${1:-}" in
  -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  "") ;;
  *) TARGET="$1" ;;
esac
[ -e "$TARGET" ] || die "path not found: $TARGET"

# Collect scripts: a single file, or every *.sh under a directory (skipping
# .git and node_modules), matching run-tests.sh's sweep.
scripts=()
if [ -f "$TARGET" ]; then
  scripts=("$TARGET")
else
  while IFS= read -r -d '' s; do scripts+=("$s"); done \
    < <(find "$TARGET" \( -type d \( -name .git -o -name node_modules \) \) -prune -o -type f -name '*.sh' -print0)
fi

[ "${#scripts[@]}" -gt 0 ] || { printf '%s[ok]%s no shell scripts under %s\n' "$YELLOW" "$RESET" "$TARGET"; exit 0; }

printf '%sshell-lint%s  %s script(s) under %s\n' "$BOLD" "$RESET" "${#scripts[@]}" "$TARGET"
fail=0
for s in "${scripts[@]}"; do
  if bash -n "$s" 2>/tmp/.shell-lint.err; then
    printf '  %s[ok]%s   %s\n' "$GREEN" "$RESET" "$s"
  else
    printf '  %s[fail]%s %s\n' "$RED" "$RESET" "$s"
    sed 's/^/        /' /tmp/.shell-lint.err
    fail=$((fail + 1))
  fi
done
rm -f /tmp/.shell-lint.err

if command -v shellcheck >/dev/null 2>&1; then
  printf '\n%sshellcheck (advisory)%s\n' "$BOLD" "$RESET"
  shellcheck -S warning "${scripts[@]}" || printf '  %s(shellcheck reported warnings above — advisory, not fatal)%s\n' "$YELLOW" "$RESET"
else
  printf '\n%s[skip]%s shellcheck not installed (advisory only); bash -n still ran\n' "$YELLOW" "$RESET"
fi

if [ "$fail" -eq 0 ]; then
  printf '%s[ok]%s all %s script(s) parse\n' "$GREEN" "$RESET" "${#scripts[@]}"; exit 0
fi
printf '%s[fail]%s %s script(s) have syntax errors\n' "$RED" "$RESET" "$fail"; exit 1

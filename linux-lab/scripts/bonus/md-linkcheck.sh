#!/usr/bin/env bash
# md-linkcheck — verify that local links in Markdown files resolve (read-only).
#
# Fills a gap: PRs add VERIFY.md / REPORT.md and docs with relative links like
# [script](../scripts/x.sh) or [guide](knowledge/setup.md). A typo'd path isn't
# caught by bash -n or the build and only surfaces as a dead link later. This
# checks every local (non-http, non-mailto, non-anchor) Markdown link against
# the filesystem, resolving it relative to the file it appears in. It never
# touches the network.
#
# Usage:
#   scripts/bonus/md-linkcheck.sh                 # every *.md under ./
#   scripts/bonus/md-linkcheck.sh linux-lab       # under a directory
#   scripts/bonus/md-linkcheck.sh README.md       # one file
#
# Exit status: 0 = all local links resolve, 1 = a broken link, 2 = usage error.
set -euo pipefail

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; BOLD=""; RESET=""
fi

die() { printf '%serror:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 2; }

TARGET="."
case "${1:-}" in
  -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  "") ;;
  *) TARGET="$1" ;;
esac
[ -e "$TARGET" ] || die "path not found: $TARGET"

files=()
if [ -f "$TARGET" ]; then
  files=("$TARGET")
else
  while IFS= read -r -d '' f; do files+=("$f"); done \
    < <(find "$TARGET" \( -type d \( -name .git -o -name node_modules \) \) -prune -o -type f -name '*.md' -print0)
fi
[ "${#files[@]}" -gt 0 ] || { printf '%s[ok]%s no Markdown files under %s\n' "$GREEN" "$RESET" "$TARGET"; exit 0; }

printf '%smd-linkcheck%s  %s file(s) under %s\n' "$BOLD" "$RESET" "${#files[@]}" "$TARGET"

broken=0; checked=0
for f in "${files[@]}"; do
  dir="$(dirname "$f")"
  # Extract the target of every [text](target) link, one per line.
  targets="$(grep -oE '\]\([^) ]+' "$f" 2>/dev/null | sed 's/^](//' || true)"
  [ -z "$targets" ] && continue
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    case "$t" in
      http://*|https://*|mailto:*|tel:*|ftp://*|\#*|'<'*) continue ;;  # external or in-page anchor
    esac
    t="${t%%#*}"      # drop #fragment
    t="${t%%\?*}"     # drop ?query
    [ -z "$t" ] && continue
    case "$t" in
      /*) resolved="$t" ;;                 # absolute-from-root (rare); check literally
      *)  resolved="$dir/$t" ;;            # relative to the file
    esac
    checked=$((checked + 1))
    if [ ! -e "$resolved" ]; then
      printf '  %s[broken]%s %s  ->  %s\n' "$RED" "$RESET" "$f" "$t"
      broken=$((broken + 1))
    fi
  done <<EOF
$targets
EOF
done

if [ "$broken" -eq 0 ]; then
  printf '%s[ok]%s %s local link(s) resolve\n' "$GREEN" "$RESET" "$checked"; exit 0
fi
printf '%s[fail]%s %s broken local link(s) of %s checked\n' "$RED" "$RESET" "$broken" "$checked"; exit 1

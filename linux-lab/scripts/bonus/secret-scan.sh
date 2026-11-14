#!/usr/bin/env bash
# secret-scan — warn about credential-shaped strings before you commit (read-only).
#
# Fills a gap: the release scripts refuse to run if a key is *tracked*, but
# contributors have nothing to catch a pasted token or exported key *before* it
# is committed. This scans for well-known credential signatures (not generic
# words, to keep false positives low) and reports file:line + the matched rule
# with the secret itself REDACTED — it never prints the secret value.
#
# Usage:
#   scripts/bonus/secret-scan.sh            # scan git-tracked text files
#   scripts/bonus/secret-scan.sh --staged   # scan only staged changes (pre-commit)
#   scripts/bonus/secret-scan.sh path ...   # scan specific files/dirs
#
# Exit status: 0 = nothing found, 1 = a likely secret found, 2 = usage error.
#
# Matching a signature does not prove a leak, and a miss does not prove safety.
# Treat hits as "look here", and never commit real credentials regardless.
set -euo pipefail

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BOLD=""; RESET=""
fi

die() { printf '%serror:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 2; }

MODE="tracked"
PATHS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --staged) MODE="staged"; shift ;;
    -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) MODE="paths"; PATHS+=("$1"); shift ;;
  esac
done

# Known credential signatures: rule|regex. Deliberately specific.
RULES=(
  'PEM private key|-----BEGIN [A-Z ]*PRIVATE KEY-----'
  'OpenSSH private key|-----BEGIN OPENSSH PRIVATE KEY-----'
  'AWS access key id|AKIA[0-9A-Z]{16}'
  'GitHub token|gh[pousr]_[0-9A-Za-z]{30,}'
  'Slack token|xox[baprs]-[0-9A-Za-z-]{10,}'
  'Google API key|AIza[0-9A-Za-z_-]{35}'
  'Generic bearer/secret assignment|(secret|token|api[_-]?key|passwd|password)[\"'\'' ]*[:=][\"'\'' ]*[A-Za-z0-9/+_=-]{16,}'
)

# Files whose matches are known-benign examples/fixtures; skipped by name.
# Test and sample files legitimately hold secret-shaped strings (e.g. the
# android-lab secret-scanner's own fixtures), so the default scan stays quiet on
# a clean tree. Use --staged for a focused pre-commit check of your own changes.
is_allowlisted() {
  case "$1" in
    *secret-scan.sh) return 0 ;;  # this scanner's own rule table matches its own patterns
    *.example|*sample*|*WARNING-test*|*test-keys*|*/tests/*|*conftest*|*fixture*|*/secrets/README.md|*.lock) return 0 ;;
    *) return 1 ;;
  esac
}

# Build the file list.
collect() {
  case "$MODE" in
    tracked) git ls-files 2>/dev/null || die "not a git repo; pass paths explicitly" ;;
    staged)  git diff --cached --name-only --diff-filter=ACM 2>/dev/null || die "not a git repo" ;;
    paths)
      for p in "${PATHS[@]}"; do
        if [ -f "$p" ]; then printf '%s\n' "$p"
        elif [ -d "$p" ]; then find "$p" \( -type d \( -name .git -o -name node_modules \) \) -prune -o -type f -print
        else die "path not found: $p"; fi
      done ;;
  esac
}

files="$(collect)"
[ -n "$files" ] || { printf '%s[ok]%s nothing to scan\n' "$GREEN" "$RESET"; exit 0; }

printf '%ssecret-scan%s  mode=%s\n' "$BOLD" "$RESET" "$MODE"
hits=0; scanned=0; skipped=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ -f "$f" ] || continue
  if is_allowlisted "$f"; then skipped=$((skipped + 1)); continue; fi
  scanned=$((scanned + 1))
  for rule in "${RULES[@]}"; do
    name="${rule%%|*}"; re="${rule#*|}"
    # -I skips binary; -n gives line numbers. Redact the matched text.
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      lineno="${line%%:*}"
      printf '  %s[hit]%s %s:%s  %s  <redacted>\n' "$RED" "$RESET" "$f" "$lineno" "$name"
      hits=$((hits + 1))
    done < <(grep -InE -e "$re" "$f" 2>/dev/null | cut -d: -f1 || true)
  done
done <<EOF
$files
EOF

if [ "$hits" -eq 0 ]; then
  printf '%s[ok]%s no credential signatures in %s file(s) (%s example/fixture file(s) skipped)\n' \
    "$GREEN" "$RESET" "$scanned" "$skipped"; exit 0
fi
printf '%s[fail]%s %s likely secret(s) across the files above — review before committing\n' "$RED" "$RESET" "$hits"
printf '%snote:%s signatures can false-positive; a hit means "look", not "confirmed leak".\n' "$YELLOW" "$RESET"
exit 1

#!/usr/bin/env bash
# deploy-page.sh — publish the dashboard (Astro, static) to GitHub Pages from your machine.
#
# No CI, no workflow files, no paid runners: the site is built locally, committed to an
# orphan `gh-pages` branch and force-pushed with `gh`. GitHub Pages then serves that branch.
# Publishes public home, Firewall/Source information, guides and community/legal pages.
# Console-backed lab controls stay local.
#
# Usage:
#   scripts/deploy-page.sh                      build + deploy to this repo's Pages
#   scripts/deploy-page.sh --dry-run            build + stage, print the folder, push nothing
#   scripts/deploy-page.sh --repo OWNER/NAME    deploy to another repo (short name = short URL,
#                                               e.g. keyvanarasteh/fw -> keyvanarasteh.github.io/fw/)
#   scripts/deploy-page.sh --branch gh-pages    target branch (default gh-pages)
#   scripts/deploy-page.sh -h|--help
#
# Needs: node + npm, git, gh (logged in with push access: `gh auth login`).
set -euo pipefail

REPO=""; BRANCH="gh-pages"; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:?--repo needs OWNER/NAME}"; shift 2 ;;
    --branch) BRANCH="${2:?--branch needs a name}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/dashboard"
RAW="$APP/build-pages.raw"      # plain astro build (gitignored, see dashboard/.gitignore)
OUT="$APP/build-pages"          # post-processed site that gets published (gitignored)

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need node; need npm; need git
if [ "$DRY" = 0 ]; then
  need gh
  gh auth status >/dev/null 2>&1 || { echo "gh is not logged in: run 'gh auth login'" >&2; exit 1; }
fi

[ -n "$REPO" ] || REPO="$(cd "$ROOT" && git remote get-url origin | sed -E 's#(https://github.com/|git@github.com:)([^/]+/[^/.]+)(\.git)?$#\2#')"
OWNER="${REPO%%/*}"; NAME="${REPO##*/}"
# <owner>.github.io repos are served from the domain root, every other repo from /<name>/
if [ "$(echo "$NAME" | tr 'A-Z' 'a-z')" = "$(echo "$OWNER" | tr 'A-Z' 'a-z').github.io" ]; then
  BASE=""; URL="https://$NAME/"
else
  BASE="/$NAME"; URL="https://$(echo "$OWNER" | tr 'A-Z' 'a-z').github.io/$NAME/"
fi
echo "==> target  $REPO ($BRANCH)  ->  $URL"

# ---- 1. build the static site with the right base path ----
[ -d "$APP/node_modules" ] || (cd "$APP" && npm ci)
rm -rf "$RAW"
echo "==> astro build (base='${BASE:-/}')"
(cd "$APP" && SITE_BASE="$BASE" PUBLIC_SITE_MODE=pages npx --no-install astro build --outDir "$RAW")
[ -f "$RAW/index.html" ] || { echo "no build in $RAW (run without --no-build)" >&2; exit 1; }
rm -rf "$OUT"; cp -R "$RAW" "$OUT"          # post-process a copy so re-runs start clean

# ---- 2. prefix the hard-coded absolute links with the base path ----
# Astro's `base` already fixes assets and <a> links it renders; the React views also contain
# literal "/firewall/"-style routes. Rewrite those in the build (idempotent: already-prefixed
# paths start with /<name>/ and no longer match). /api is left alone: there is no backend here.
if [ -n "$BASE" ]; then
  echo "==> prefixing route literals with $BASE"
  export BASE
  find "$OUT" -type f \( -name '*.html' -o -name '*.js' -o -name '*.css' \) -print0 |
    xargs -0 perl -pi -e '
      s!(["\x27`(=])/(tr|de|fr|es|it|fa|ar|source|cleanup|how-to-use|feedback|firewall|android|labs|jobs|contribute|legal|apk-lab|favicon\.svg|_astro)(?=[/"\x27`#?)\s>])!$1$ENV{BASE}/$2!g;
      s{(href=["\x27]|href:\s*["\x27])/(?=["\x27])}{$1$ENV{BASE}/}g;
    '
fi

# ---- 3. keep only routes usable without the local console ----
for path in "$OUT"/*; do
  case "$(basename "$path")" in
    index.html|404.html|favicon.svg|_astro|firewall|source|cleanup|how-to-use|contribute|legal|feedback|.nojekyll) ;;
    tr|de|fr|es|it|fa|ar)
      find "$path" -mindepth 1 -maxdepth 1 ! -name index.html ! -name firewall ! -name source ! -name cleanup ! -name how-to-use ! -name contribute ! -name legal ! -name feedback -exec rm -rf {} + ;;
    *) rm -rf "$path" ;;
  esac
done
touch "$OUT/.nojekyll"                      # keep the _astro/ folder (Jekyll skips "_" dirs)

if [ "$DRY" = 1 ]; then
  echo "==> dry run: staged in $OUT ($(find "$OUT" -type f | wc -l | tr -d ' ') files), nothing pushed"
  exit 0
fi

# ---- 4. commit as a single orphan commit and force-push the branch ----
SRC_SHA="$(cd "$ROOT" && git rev-parse --short HEAD)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cp -R "$OUT/." "$TMP/"
(
  cd "$TMP"
  git init -q -b "$BRANCH"
  git add -A
  git -c user.name="$(git -C "$ROOT" config user.name || echo deploy)" \
      -c user.email="$(git -C "$ROOT" config user.email || echo deploy@localhost)" \
      commit -q -m "deploy: dashboard @ $SRC_SHA ($(date -u +%Y-%m-%dT%H:%MZ))"
  echo "==> pushing $BRANCH"
  git -c credential.helper= -c credential.helper='!gh auth git-credential' \
      push -q --force "https://github.com/$REPO.git" "$BRANCH"
)

# ---- 5. make sure Pages serves that branch (no-op when already set) ----
echo "==> enabling GitHub Pages ($BRANCH, /)"
gh api -X POST "repos/$REPO/pages" -f "source[branch]=$BRANCH" -f "source[path]=/" >/dev/null 2>&1 ||
  gh api -X PUT "repos/$REPO/pages" -f "source[branch]=$BRANCH" -f "source[path]=/" >/dev/null 2>&1 || true

# ---- 6. wait for the (free, GitHub-run) Pages build ----
for i in $(seq 1 30); do
  st="$(gh api "repos/$REPO/pages/builds/latest" -q .status 2>/dev/null || echo unknown)"
  [ "$st" = "built" ] && { echo "==> live: $URL"; exit 0; }
  [ "$st" = "errored" ] && { echo "Pages build errored: gh api repos/$REPO/pages/builds/latest" >&2; exit 1; }
  sleep 5
done
echo "==> pushed; Pages is still building. It will appear at $URL"

#!/usr/bin/env bash
# Build, sign, notarize and (optionally) publish the os-lab macOS app as a universal DMG.
#
#   app/scripts/release-mac.sh                 build + sign + notarize + verify, upload nothing
#   app/scripts/release-mac.sh --publish       ...and create/update the GitHub release app-v<version>
#   app/scripts/release-mac.sh --no-notarize   build + sign only (no Apple upload) for a local check
#   app/scripts/release-mac.sh --arch arm64    one architecture instead of universal
#
# Credentials never live in the repository. They come from the environment, from the git-ignored
# secrets/ folder (see secrets/README.md), or from the login keychain. This script prints which
# source it used, never the values.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$APP_DIR/.." && pwd)"
SLUG="keyvanarasteh/os-lab"
PUBLISH=0; NOTARIZE=1; TARGET="universal-apple-darwin"

while [ $# -gt 0 ]; do
  case "$1" in
    --publish) PUBLISH=1 ;;
    --no-notarize) NOTARIZE=0 ;;
    --arch) shift; case "${1:-}" in arm64) TARGET=aarch64-apple-darwin ;; x64) TARGET=x86_64-apple-darwin ;; universal) ;; *) echo "--arch arm64|x64|universal" >&2; exit 2 ;; esac ;;
    -h|--help) sed -n 2,12p "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

die() { echo "error: $*" >&2; exit 1; }
say() { echo "==> $*"; }

[ "$(uname -s)" = Darwin ] || die "macOS only: signing and notarization need Xcode's tools"
for t in node npm cargo xcrun codesign security hdiutil shasum; do command -v "$t" >/dev/null || die "$t not found"; done
if [ "$PUBLISH" = 1 ]; then command -v gh >/dev/null && gh auth status >/dev/null 2>&1 || die "--publish needs the gh CLI, logged in"; fi

VERSION="$(node -p "require('$APP_DIR/src-tauri/tauri.conf.json').version")"
TAG="app-v$VERSION"
OUT="$APP_DIR/out/$VERSION"
if [ "$PUBLISH" = 1 ]; then
  # --force: CI checks out the tag ref, so the tag already exists locally and a plain
  # fetch is rejected for clobbering it. Fall back to an already-present local tag.
  git -C "$REPO" fetch -q --force origin "refs/tags/$TAG:refs/tags/$TAG" 2>/dev/null \
    || git -C "$REPO" rev-parse -q --verify "refs/tags/$TAG^{commit}" >/dev/null \
    || die "release tag $TAG is missing"
  [ "$(git -C "$REPO" rev-list -n 1 "$TAG")" = "$(git -C "$REPO" rev-parse HEAD)" ] \
    || die "$TAG does not point to this checkout; publish from the tagged commit"
fi

# ── 1. Secrets must never be tracked ────────────────────────────────────────────────────────────
TRACKED="$(git -C "$REPO" ls-files -- secrets | grep -v '^secrets/README.md$' || true)"
[ -z "$TRACKED" ] || die "tracked files under secrets/ (remove them from git, rotate the keys):
$TRACKED"
if git -C "$REPO" ls-files -- '*.p8' '*.p12' '*.mobileprovision' '*.pem' | grep -q .; then
  die "a key or certificate file is tracked by git"
fi

# ── 2. Locate credentials ───────────────────────────────────────────────────────────────────────
cred_dirs=()
[ -n "${OSLAB_SECRETS_DIR:-}" ] && cred_dirs+=("$OSLAB_SECRETS_DIR")
cred_dirs+=("$REPO/secrets/cupertino/credentials" "$REPO/secrets/cupertino" "$REPO/../qLar/secrets/cupertino/credentials")

first_file() { # name... → first existing file under any credential dir
  local d n
  for d in "${cred_dirs[@]}"; do for n in "$@"; do [ -f "$d/$n" ] && { echo "$d/$n"; return; }; done; done
}
first_value() { local f; f="$(first_file "$@")"; [ -n "$f" ] && tr -d '[:space:]' < "$f" || true; }

if [ -z "${APPLE_API_KEY_PATH:-}" ]; then
  for d in "${cred_dirs[@]}"; do
    p="$(ls "$d"/app-store-connect/AuthKey_*.p8 2>/dev/null | head -1 || true)"
    [ -n "$p" ] && { APPLE_API_KEY_PATH="$p"; src_note="secrets folder"; break; }
  done
fi
: "${APPLE_API_KEY:=$(first_value app-store-connect/key-id.txt app-store-connect/keyId.key)}"
: "${APPLE_API_ISSUER:=$(first_value app-store-connect/issuer-id.txt app-store-connect/IssuerId.key)}"

if [ -z "${APPLE_SIGNING_IDENTITY:-}" ]; then
  APPLE_SIGNING_IDENTITY="$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application: [^"]*\)".*/\1/p' | head -1)"
fi
[ -n "${APPLE_SIGNING_IDENTITY:-}" ] || [ -n "${APPLE_CERTIFICATE:-}" ] || die "no Developer ID Application identity in the keychain, and no APPLE_CERTIFICATE"

say "version $VERSION, tag $TAG, target $TARGET"
say "signing identity: ${APPLE_SIGNING_IDENTITY:-from APPLE_CERTIFICATE}"
if [ "$NOTARIZE" = 1 ]; then
  [ -f "${APPLE_API_KEY_PATH:-}" ] && [ -n "${APPLE_API_KEY:-}" ] && [ -n "${APPLE_API_ISSUER:-}" ] \
    || die "notarization needs APPLE_API_KEY, APPLE_API_ISSUER and APPLE_API_KEY_PATH (see secrets/README.md), or pass --no-notarize"
  say "notarization key: id ${APPLE_API_KEY} (.p8 found)"
  export APPLE_API_KEY APPLE_API_ISSUER APPLE_API_KEY_PATH
else
  say "notarization skipped (--no-notarize)"
  unset APPLE_API_KEY APPLE_API_ISSUER APPLE_API_KEY_PATH
fi
export APPLE_SIGNING_IDENTITY
# Cargo must not strip host proc-macro dylibs; doing so breaks some macOS toolchains with E0463.
export CARGO_PROFILE_RELEASE_STRIP=false

# ── 3. Build ────────────────────────────────────────────────────────────────────────────────────
cd "$APP_DIR"
say "installing build tools"
npm ci --no-audit --no-fund >/dev/null
say "installing dashboard build tools"
npm ci --no-audit --no-fund --prefix "$APP_DIR/../dashboard" >/dev/null
say "staging the runtime and dashboard"
node scripts/stage-runtime.mjs
[ -n "${APPLE_SIGNING_IDENTITY:-}" ] || die "bundled Python helpers need a Developer ID identity in the keychain; import APPLE_CERTIFICATE before building"
node scripts/stage-python-helper.mjs
if [ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ] && [ -f "$REPO/secrets/updater/os-lab.key" ]; then
  export TAURI_SIGNING_PRIVATE_KEY="$(cat "$REPO/secrets/updater/os-lab.key")"
fi
[ -n "${TAURI_SIGNING_PRIVATE_KEY:-}" ] || die "updater signing key is missing (TAURI_SIGNING_PRIVATE_KEY)"
say "building ($TARGET) — Tauri signs the app with hardened runtime and notarizes it when the API key is set"
npx tauri build --target "$TARGET" --bundles app

BUNDLE="${CARGO_TARGET_DIR:-$APP_DIR/src-tauri/target}/$TARGET/release/bundle"
ARCH_LABEL="${TARGET%%-apple-darwin}"
APP="$BUNDLE/macos/os-lab.app"
DMG="$BUNDLE/dmg/os-lab_${VERSION}_${ARCH_LABEL}.dmg"
UPDATE="$BUNDLE/macos/os-lab.app.tar.gz"
[ -d "$APP" ] && [ -f "$UPDATE" ] && [ -f "$UPDATE.sig" ] \
  || die "build produced no app or signed updater bundle"

# Package the DMG ourselves. Tauri's bundle_dmg.sh mounts a read-write volume and runs
# Finder to lay out icons, then frequently cannot unmount it ("hdiutil: Resource busy"),
# which failed every macOS release on the build host. Create a compressed DMG straight
# from the signed, notarized .app with no interstitial read-write mount to get stuck.
say "packaging the DMG from the signed app"
mkdir -p "$(dirname "$DMG")"
rm -f "$DMG"
DMG_STAGE="$(mktemp -d)"
cp -R "$APP" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
hdiutil create -volname "os-lab" -srcfolder "$DMG_STAGE" -fs HFS+ -format UDZO -ov "$DMG"
rm -rf "$DMG_STAGE"
[ -f "$DMG" ] || die "DMG packaging failed"

# ── 4. Sign + notarize the DMG itself (Tauri notarizes the .app) ────────────────────────────────
say "signing the DMG"
codesign --force --sign "$APPLE_SIGNING_IDENTITY" --timestamp "$DMG"
if [ "$NOTARIZE" = 1 ]; then
  say "notarizing the DMG (waits for Apple)"
  xcrun notarytool submit "$DMG" --key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY" --issuer "$APPLE_API_ISSUER" --wait
  xcrun stapler staple "$DMG"
  xcrun stapler staple "$APP" >/dev/null 2>&1 || true
fi

# ── 5. Verify what will ship ────────────────────────────────────────────────────────────────────
say "verifying"
codesign --verify --deep --strict --verbose=1 "$APP"
codesign --verify --verbose=1 "$DMG"
if [ "$NOTARIZE" = 1 ]; then
  xcrun stapler validate "$APP"
  xcrun stapler validate "$DMG"
  spctl --assess --type exec --verbose=2 "$APP"
  spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
fi

# ── 6. Collect ──────────────────────────────────────────────────────────────────────────────────
mkdir -p "$OUT"
ASSET="$OUT/os-lab_${VERSION}_macos_${ARCH_LABEL}.dmg"
cp "$DMG" "$ASSET"
( cd "$OUT" && shasum -a 256 "$(basename "$ASSET")" > "$(basename "$ASSET").sha256" )
say "ready: $ASSET"
cat "$ASSET.sha256"
npx tauri signer sign --app-version "$VERSION" "$ASSET" >/dev/null
[ -f "$ASSET.sig" ] || die "DMG signature is missing"
UPDATE_ASSET="$OUT/os-lab_${VERSION}_macos_${ARCH_LABEL}.app.tar.gz"
cp "$UPDATE" "$UPDATE_ASSET"
cp "$UPDATE.sig" "$UPDATE_ASSET.sig"
( cd "$OUT" && shasum -a 256 "$(basename "$UPDATE_ASSET")" > "$(basename "$UPDATE_ASSET").sha256" )

# ── 7. Publish ──────────────────────────────────────────────────────────────────────────────────
if [ "$PUBLISH" = 1 ]; then
  [ "$NOTARIZE" = 1 ] || die "refusing to publish an un-notarized DMG"
  if gh release view "$TAG" -R "$SLUG" >/dev/null 2>&1; then
    say "updating release $TAG"
    gh release upload "$TAG" "$ASSET" "$ASSET.sha256" "$ASSET.sig" "$UPDATE_ASSET" "$UPDATE_ASSET.sig" "$UPDATE_ASSET.sha256" --clobber -R "$SLUG"
  else
    say "creating release $TAG"
    gh release create "$TAG" "$ASSET" "$ASSET.sha256" "$ASSET.sig" "$UPDATE_ASSET" "$UPDATE_ASSET.sig" "$UPDATE_ASSET.sha256" -R "$SLUG" --title "os-lab app $VERSION" \
      --notes "os-lab desktop app $VERSION. One installer per platform, each with a .sha256 file. The macOS DMG is universal, signed and notarized. The app can download managed Python on request."
  fi
  say "published: https://github.com/$SLUG/releases/tag/$TAG"
else
  say "dry run: nothing uploaded (use --publish)"
fi

#!/usr/bin/env node
// Publish the Tauri updater feed (`app-updates/latest.json`) for a released app version.
//
// "Smart" modes:
//   node scripts/publish-app-update.mjs                  version from app/src-tauri/tauri.conf.json
//   node scripts/publish-app-update.mjs 0.2.7            explicit version
//   node scripts/publish-app-update.mjs --detect-latest  newest app-v* release with a complete asset set
//
// Assets are read from app/out/<version> when every file is present, otherwise downloaded from the
// GitHub release with `gh`. Every SHA-256 is checked by app/scripts/build-update-manifest.mjs, and
// the feed is uploaded to the `app-updates` prerelease. Detection uses the GitHub API, so it works
// in CI and from a shallow checkout. Publishing is idempotent and never downgrades a newer feed.
// GitHub itself marks the newest non-prerelease as Latest; pass --mark-latest to set it explicitly.
//
//   --detect-latest   auto-detect the newest release with all platform assets
//   --allow-none      with --detect-latest, exit 0 when no release is complete yet (scheduled CI)
//   --check           print the detected/complete version without downloading or publishing
//   --dir <path>      read assets from this folder instead of app/out/<version>
//   --mark-latest     mark app-v<version> as the GitHub Latest release
//   --verify          verify every updater signature with app/UPDATER_MINISIGN.pub (needs minisign)
//   --force           publish even when the feed already has the same or a newer version
//   --dry-run         build the feed but do not upload
//   --repo <slug>     default keyvanarasteh/os-lab

import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..");
let slug = "keyvanarasteh/os-lab";
let detectLatest = false;
let markLatest = false;
let dryRun = false;
let assetDir = null;
let version = null;
let allowNone = false;
let checkOnly = false;
let verify = false;
let force = false;

const args = process.argv.slice(2);
for (let i = 0; i < args.length; i += 1) {
  const arg = args[i];
  if (arg === "--detect-latest") detectLatest = true;
  else if (arg === "--allow-none") allowNone = true;
  else if (arg === "--check") checkOnly = true;
  else if (arg === "--mark-latest") markLatest = true;
  else if (arg === "--verify") verify = true;
  else if (arg === "--force") force = true;
  else if (arg === "--dry-run") dryRun = true;
  else if (arg === "--dir") assetDir = resolve(args[++i] || "");
  else if (arg === "--repo") slug = args[++i] || slug;
  else if (arg === "-h" || arg === "--help") {
    console.log("usage: publish-app-update.mjs [version] [--detect-latest] [--allow-none] [--check] [--dir <path>] [--mark-latest] [--verify] [--force] [--dry-run] [--repo <slug>]");
    process.exit(0);
  } else if (!arg.startsWith("-")) version = arg.replace(/^app-v/, "");
  else {
    console.error(`unknown option: ${arg}`);
    process.exit(2);
  }
}

function run(command, list, options = {}) {
  return execFileSync(command, list, { cwd: repo, encoding: "utf8", stdio: options.quiet ? "pipe" : "inherit", ...options });
}

function gh(list, options = {}) {
  return run("gh", list, options);
}

export function assetNames(v) {
  return [
    `os-lab_${v}_macos_universal.app.tar.gz`,
    `os-lab_${v}_windows_x64-setup.exe`,
    `os-lab_${v}_linux_amd64.AppImage`,
    `os-lab_${v}_linux_arm64.AppImage`,
  ];
}

function releaseAssets(v) {
  try {
    const json = gh(["api", `repos/${slug}/releases/tags/app-v${v}`], { quiet: true });
    return JSON.parse(json).assets.map((asset) => asset.name);
  } catch {
    return null;
  }
}

export function complete(assets, v) {
  if (!assets) return false;
  const have = new Set(assets);
  return assetNames(v).every((name) => have.has(name) && have.has(`${name}.sha256`) && have.has(`${name}.sig`));
}

export function compareVersions(a, b) {
  const [mainA, preA] = a.split("-", 2);
  const [mainB, preB] = b.split("-", 2);
  const partsA = mainA.split(".").map(Number);
  const partsB = mainB.split(".").map(Number);
  for (let i = 0; i < Math.max(partsA.length, partsB.length); i += 1) {
    const delta = (partsA[i] || 0) - (partsB[i] || 0);
    if (delta) return delta;
  }
  if (preA === preB) return 0;
  if (!preA) return 1;
  if (!preB) return -1;
  return preA.localeCompare(preB);
}

function releases() {
  return JSON.parse(gh(["api", `repos/${slug}/releases?per_page=100`], { quiet: true }));
}

function detectedVersion() {
  const candidates = releases()
    .filter((release) => !release.draft && !release.prerelease && /^app-v\d/.test(release.tag_name))
    .map((release) => release.tag_name.replace(/^app-v/, ""))
    .sort(compareVersions)
    .reverse();
  for (const candidate of candidates) {
    if (complete(releaseAssets(candidate), candidate)) {
      console.log(`detected latest complete release: app-v${candidate}`);
      return candidate;
    }
    console.log(`skipping app-v${candidate}: assets are incomplete`);
  }
  if (allowNone) {
    console.log("no app-v* release has a complete signed asset set yet; nothing to publish");
    return null;
  }
  throw new Error("no app-v* release has a complete set of release assets");
}

function currentFeed() {
  const directory = mkdtempSync(join(tmpdir(), "oslab-feed-"));
  try {
    gh(["release", "download", "app-updates", "--repo", slug, "--pattern", "latest.json", "--dir", directory], { quiet: true });
    return JSON.parse(readFileSync(join(directory, "latest.json"), "utf8"));
  } catch {
    return null;
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

function sameFeed(a, b) {
  return Boolean(a) && a.version === b.version && JSON.stringify(a.platforms) === JSON.stringify(b.platforms);
}

function configuredVersion() {
  const conf = JSON.parse(readFileSync(join(repo, "app", "src-tauri", "tauri.conf.json"), "utf8"));
  return conf.version;
}

if (detectLatest) {
  version = detectedVersion();
  if (!version) process.exit(0);
} else if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(version || "")) {
  version = configuredVersion();
}
if (!version) throw new Error("could not determine the app version");
if (checkOnly) {
  const ready = complete(releaseAssets(version), version);
  console.log(`${ready ? "ready" : "incomplete"}: app-v${version}`);
  process.exit(ready ? 0 : 1);
}
console.log(`publishing updater feed for ${version}`);

let directory = assetDir || join(repo, "app", "out", version);
const needed = assetNames(version).flatMap((name) => [name, `${name}.sha256`, `${name}.sig`]);
const localComplete = needed.every((name) => existsSync(join(directory, name)));
let temporary = null;
if (!localComplete) {
  if (!complete(releaseAssets(version), version)) throw new Error(`app-v${version} is missing release assets`);
  temporary = mkdtempSync(join(tmpdir(), `oslab-assets-${version}-`));
  console.log(`downloading release assets into ${temporary}`);
  gh(["release", "download", `app-v${version}`, "--repo", slug, "--dir", temporary, ...needed.flatMap((name) => ["--pattern", name])]);
  directory = temporary;
}

const outputDir = mkdtempSync(join(tmpdir(), `oslab-manifest-${version}-`));
const output = join(outputDir, "latest.json");
try {
  run("node", [join(repo, "app", "scripts", "build-update-manifest.mjs"), version, directory, output]);
  if (verify) {
    const verifier = join(repo, "app", "scripts", "verify-release-signature.py");
    for (const name of assetNames(version)) {
      run("python3", [verifier, join(directory, name), "--version", version]);
    }
    console.log("verified every updater signature");
  }
  const next = JSON.parse(readFileSync(output, "utf8"));
  if (dryRun) {
    console.log(readFileSync(output, "utf8"));
    console.log("dry run: nothing uploaded");
  } else {
    const current = currentFeed();
    if (!force && current && compareVersions(next.version, current.version) < 0) {
      console.log(`feed already points to ${current.version}; not downgrading to ${version}`);
    } else if (!force && sameFeed(current, next)) {
      console.log(`feed already points to ${version}; nothing to upload`);
    } else {
      let exists = true;
      try {
        gh(["release", "view", "app-updates", "--repo", slug], { quiet: true });
      } catch {
        exists = false;
      }
      if (!exists) {
        gh(["release", "create", "app-updates", "--repo", slug, "--prerelease", "--title", "os-lab app update feed",
          "--notes", "Signed app update manifests. Written by scripts/publish-app-update.mjs."]);
      }
      gh(["release", "upload", "app-updates", output, "--clobber", "--repo", slug]);
      if (markLatest) gh(["release", "edit", `app-v${version}`, "--latest", "--repo", slug]);
      console.log(`published app-updates/latest.json for ${version}`);
    }
  }
} finally {
  if (temporary) rmSync(temporary, { recursive: true, force: true });
  rmSync(outputDir, { recursive: true, force: true });
}

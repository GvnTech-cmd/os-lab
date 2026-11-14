#!/usr/bin/env node
// Stage the os-lab runtime the app bundles: src-tauri/resources/os-lab/.
//
// What goes in: git-tracked files of the labs, the console and labctl (never untracked or
// ignored files, so .env, profiles, VM disks and local notes cannot slip in), plus a fresh
// dashboard build. The app copies this tree into its data folder on first launch
// (src-tauri/src/runtime.rs), where the labs can write their own state.
//
//   node scripts/stage-runtime.mjs            build the dashboard, then stage
//   node scripts/stage-runtime.mjs --no-build stage the committed dashboard/dist instead

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, statSync, copyFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..", "..");
const out = resolve(here, "..", "src-tauri", "resources", "os-lab");

// Tracked top-level paths the console and the labs need at run time.
export const INCLUDE = ["labctl", "console", "source-lab", "cleanup-lab", "android-lab", "linux-lab", "win-lab", "ios-lab", "firewall-lab", "docs/legal", "LICENSE"];

// These are the entry points used by the installed console and every supported lab path.
export const REQUIRED = [
  "cleanup-lab/engine/cleanup_lab/__init__.py",
  "cleanup-lab/engine/cleanup_lab/cli.py",
  "cleanup-lab/catalog/schema.json",
  "cleanup-lab/catalog/system.json",
  "source-lab/engine/source_lab/import_legacy.py",
  "source-lab/acceptance.py",
  "source-lab/run.py", "source-lab/list_inputs.py", "source-lab/contracts/schema.json",
  "source-lab/engine/source_lab/cli/run_detection.py", "source-lab/engine/source_lab/paths.py",
  "source-lab/engine/source_lab/collectors/browser/canary.js", "console/source_api.py",
  "console/source_control.py", "console/source_jobs.py", "console/source_worker.py",
  "console/source_artifacts.py", "console/source_overview.py", "console/source_manifest_specs.json", "console/source_pipeline.json",
  "labctl", "console/oslab.py", "console/content.py", "console/capabilities.json", "android-lab/lab/web_ui.py",
  "android-lab/lab/scripts/setup-ubuntu.sh", "android-lab/lab/docker-compose.yml",
  "android-lab/lab/scripts/preflight.sh", "android-lab/lab/scripts/install-service.sh",
  "android-lab/lab/scripts/uninstall-service.sh", "android-lab/lab/.env.example",
  "win-lab/scripts/setup-ubuntu.sh", "win-lab/docker-compose.yml",
  "win-lab/scripts/preflight.sh", "win-lab/scripts/backup.sh",
  "win-lab/scripts/install-service.sh", "win-lab/scripts/uninstall-service.sh", "win-lab/.env.example",
  "linux-lab/scripts/setup-ubuntu.sh", "linux-lab/docker-compose.yml",
  "linux-lab/scripts/preflight.sh", "linux-lab/scripts/backup.sh",
  "linux-lab/scripts/install-service.sh", "linux-lab/scripts/uninstall-service.sh", "linux-lab/.env.example",
  "ios-lab/scripts/setup-ubuntu.sh", "ios-lab/docker-compose.yml",
  "ios-lab/scripts/preflight.sh", "ios-lab/scripts/backup.sh",
  "ios-lab/scripts/install-service.sh", "ios-lab/scripts/uninstall-service.sh", "ios-lab/.env.example",
  "ios-lab/mac/setup-mac.sh", "ios-lab/mac/doctor-mac.sh", "ios-lab/mac/run-simulator.sh",
  "ios-lab/mac/stop-simulator.sh", "ios-lab/mac/appium.sh", "ios-lab/mac/config.env.example",
  "docs/legal/PRIVACY.md",
];

// Even tracked, these never ship: credentials, private notes, VM guest data.
const NEVER = [
  /^source-lab\/(?:resources|legacy|imports)\//,
  /^source-lab\/.*\.(?:zip|apk|ipa|exe|dll|dmg|db|sqlite|xlsx)$/i,
  /(^|\/)\.env$/,
  /(^|\/)config\.env$/,
  /\.local\.md$/,
  /\.(pem|key|p12|pfx|keystore|jks)$/i,
  /(^|\/)id_(rsa|ed25519|ecdsa)/,
  /(^|\/)storage\//,
  /(^|\/)\.private\//,
];

export function allowed(path) {
  return !NEVER.some((re) => re.test(path));
}

export function select(tracked) {
  return tracked.filter((p) => allowed(p) && INCLUDE.some((root) => p === root || p.startsWith(root + "/")));
}

export function missingRequired(selected) {
  const files = new Set(selected);
  return REQUIRED.filter((path) => !files.has(path) || !existsSync(join(repo, path)));
}

function trackedFiles() {
  const raw = execFileSync("git", ["-C", repo, "ls-files", "-z", "--", ...INCLUDE], { maxBuffer: 64 * 1024 * 1024 });
  return select(raw.toString("utf8").split("\0").filter(Boolean));
}

function buildDashboard() {
  // Inside the repo, not the system temp dir: Astro renames files into outDir, which fails across volumes.
  const dest = join(repo, "dashboard", ".app-stage-build");
  rmSync(dest, { recursive: true, force: true });
  const env = { ...process.env };
  delete env.SITE_BASE; // the app serves from /, not from a GitHub Pages sub-path
  execFileSync("npx", ["astro", "build", "--outDir", dest], { cwd: join(repo, "dashboard"), stdio: "inherit", env, shell: process.platform === "win32" });
  return dest;
}

function listFiles(dir) {
  const found = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) found.push(...listFiles(p));
    else found.push(p);
  }
  return found;
}

function main() {
  const noBuild = process.argv.includes("--no-build");
  const dist = noBuild ? join(repo, "dashboard", "dist") : buildDashboard();
  try {
    stage(dist);
  } finally {
    if (!noBuild) rmSync(dist, { recursive: true, force: true });
  }
}

function stage(dist) {
  if (!existsSync(join(dist, "index.html"))) throw new Error(`no dashboard build at ${dist}`);

  const selected = trackedFiles();
  const missing = missingRequired(selected);
  if (missing.length) throw new Error(`required bundled files are missing: ${missing.join(", ")}`);

  rmSync(out, { recursive: true, force: true });
  mkdirSync(out, { recursive: true });

  let count = 0;
  for (const rel of selected) {
    const from = join(repo, rel);
    if (!existsSync(from)) throw new Error(`tracked bundled file is missing: ${rel}`);
    const to = join(out, rel);
    mkdirSync(dirname(to), { recursive: true });
    copyFileSync(from, to); // copyFileSync keeps the mode, so labctl stays executable
    count++;
  }
  const distOut = join(out, "dashboard", "dist");
  cpSync(dist, distOut, { recursive: true });
  const distCount = listFiles(distOut).length;

  // A Tauri resource folder must not be empty, and the app checks the version stamp itself.
  writeFileSync(join(out, "STAGED.txt"), `Staged from ${relative(process.cwd(), repo) || "."}: ${count} files + ${distCount} dashboard files.\n`);
  console.log(`staged ${count} tracked files and ${distCount} dashboard files into ${relative(process.cwd(), out)}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();

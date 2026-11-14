import assert from "node:assert/strict";
import { test } from "node:test";
import { allowed, missingRequired, REQUIRED, select } from "./stage-runtime.mjs";
import { readFileSync } from "node:fs";
import { join } from "node:path";

test("secrets and local state never ship, even when tracked", () => {
  for (const p of ["android-lab/lab/.env", "ios-lab/mac/config.env", "x/notes.local.md", "a/b/key.pem", "win-lab/storage/disk.img", "linux-lab/id_rsa", ".private/x"]) {
    assert.equal(allowed(p), false, p);
  }
  for (const p of ["android-lab/lab/.env.example", "ios-lab/mac/config.env.example", "console/oslab.py"]) {
    assert.equal(allowed(p), true, p);
  }
});

test("only the runtime roots are selected", () => {
  const got = select(["labctl", "console/oslab.py", "dashboard/src/x.ts", "README.md", "firewall-lab/catalog.json", "docs/legal/PRIVACY.md", "android-lab/lab/.env", "app/package.json", "labctl-other"]);
  assert.deepEqual(got, ["labctl", "console/oslab.py", "firewall-lab/catalog.json", "docs/legal/PRIVACY.md"]);
});

test("the bundle includes every console and lab entry point", () => {
  assert.deepEqual(missingRequired(REQUIRED), []);
  assert.deepEqual(missingRequired(REQUIRED.filter((p) => p !== "labctl")), ["labctl"]);
});

test("launcher grants each Tauri command it calls", () => {
  const base = join(import.meta.dirname, "..");
  const launcher = readFileSync(join(base, "ui", "launcher.js"), "utf8");
  const capability = JSON.parse(readFileSync(join(base, "src-tauri", "capabilities", "launcher.json"), "utf8"));
  const manifest = readFileSync(join(base, "src-tauri", "build.rs"), "utf8");
  const declared = readFileSync(join(base, "src-tauri", "permissions", "app_updates.toml"), "utf8");
  const commands = [...launcher.matchAll(/invoke\("([a-z_]+)"/g)].map((match) => match[1]);
  for (const command of commands) {
    assert.ok(capability.permissions.includes(`allow-${command.replaceAll("_", "-")}`), command);
    assert.ok(manifest.includes(`"${command}"`) || declared.includes(`"${command}"`), command);
  }
});

test("the container warning has an explicit, persistent opt-out", () => {
  const base = join(import.meta.dirname, "..");
  const html = readFileSync(join(base, "ui", "index.html"), "utf8");
  const launcher = readFileSync(join(base, "ui", "launcher.js"), "utf8");
  assert.match(html, /id="dont-show-row"[^>]*hidden/);
  assert.match(launcher, /container_warning_hidden/);
  assert.match(launcher, /container_warning_set_hidden/);
});

test("Source Lab ships with its core and private state is excluded", () => {
  const selected = select(["source-lab/run.py", "source-lab/list_inputs.py", "source-lab/engine/source_lab/paths.py", "source-lab/engine/source_lab/collectors/browser/canary.js", "source-lab/storage/control/session-hmac.key", "source-lab/resources/private.csv", "source-lab/legacy/snapshot.json", "source-lab/targets/third-party.apk"]);
  assert.deepEqual(selected, ["source-lab/run.py", "source-lab/list_inputs.py", "source-lab/engine/source_lab/paths.py", "source-lab/engine/source_lab/collectors/browser/canary.js"]);
  for (const path of ["source-lab/run.py", "source-lab/list_inputs.py", "console/source_api.py", "console/source_manifest_specs.json"]) assert.ok(REQUIRED.includes(path), path);
});

test("Cleanup Lab engine and catalog ship with the desktop runtime", () => {
  const selected = select([
    "cleanup-lab/engine/cleanup_lab/__init__.py",
    "cleanup-lab/engine/cleanup_lab/cli.py",
    "cleanup-lab/catalog/system.json",
    "cleanup-lab/storage/history.sqlite3",
    "cleanup-lab/.private/history.key",
  ]);
  assert.deepEqual(selected, [
    "cleanup-lab/engine/cleanup_lab/__init__.py",
    "cleanup-lab/engine/cleanup_lab/cli.py",
    "cleanup-lab/catalog/system.json",
  ]);
  for (const path of selected) assert.ok(REQUIRED.includes(path), path);
});

//! Where the os-lab files live.
//!
//! The console (`android-lab/lab/web_ui.py`) works relative to its own checkout: it serves
//! `dashboard/dist` and the labs write their state (`storage/`, `.env`, artifacts) beside their
//! scripts. An installed app's resource folder is read-only, so the bundled copy is synced into
//! the app's data folder first, and the console runs from there.
//!
//! Resolution order:
//! 1. `OSLAB_ROOT` (environment) — a checkout you point at.
//! 2. the checkout chosen in the app (`console_choose_root`, remembered in the store).
//! 3. a development checkout: the parent of `app/` when run from `cargo run` / `tauri dev`.
//! 4. the bundled runtime, synced into `<app data>/os-lab`.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

/// A folder is an os-lab root when it has the launcher, the console module and the web console.
pub fn is_root(dir: &Path) -> bool {
    dir.join("labctl").is_file()
        && dir.join("console").join("oslab.py").is_file()
        && dir.join("android-lab").join("lab").join("web_ui.py").is_file()
}

const BUNDLE_FILES: &[&str] = &[
    "source-lab/engine/source_lab/import_legacy.py",
    "source-lab/run.py",
    "source-lab/list_inputs.py",
    "source-lab/engine/source_lab/cli/run_detection.py",
    "source-lab/engine/source_lab/collectors/browser/canary.js",
    "console/source_api.py",
    "console/source_control.py",
    "console/source_jobs.py",
    "console/source_worker.py",
    "console/source_artifacts.py",
    "console/source_overview.py",
    "console/source_manifest_specs.json",
    "console/source_pipeline.json",
    "console/content.py",
    "dashboard/dist/index.html",
    "docs/legal/PRIVACY.md",
    "android-lab/lab/scripts/setup-ubuntu.sh",
    "android-lab/lab/scripts/preflight.sh",
    "android-lab/lab/scripts/install-service.sh",
    "android-lab/lab/scripts/uninstall-service.sh",
    "android-lab/lab/docker-compose.yml",
    "win-lab/scripts/setup-ubuntu.sh",
    "win-lab/scripts/preflight.sh",
    "win-lab/scripts/backup.sh",
    "win-lab/scripts/install-service.sh",
    "win-lab/scripts/uninstall-service.sh",
    "win-lab/docker-compose.yml",
    "linux-lab/scripts/setup-ubuntu.sh",
    "linux-lab/scripts/preflight.sh",
    "linux-lab/scripts/backup.sh",
    "linux-lab/scripts/install-service.sh",
    "linux-lab/scripts/uninstall-service.sh",
    "linux-lab/docker-compose.yml",
    "ios-lab/scripts/setup-ubuntu.sh",
    "ios-lab/scripts/preflight.sh",
    "ios-lab/scripts/backup.sh",
    "ios-lab/scripts/install-service.sh",
    "ios-lab/scripts/uninstall-service.sh",
    "ios-lab/docker-compose.yml",
    "ios-lab/mac/setup-mac.sh",
    "ios-lab/mac/doctor-mac.sh",
    "ios-lab/mac/run-simulator.sh",
    "ios-lab/mac/stop-simulator.sh",
    "ios-lab/mac/appium.sh",
];

/// A staged installer must contain the console, dashboard, legal baseline and lab entry points.
fn is_complete_bundle(dir: &Path) -> bool {
    is_root(dir) && BUNDLE_FILES.iter().all(|path| dir.join(path).is_file())
}

#[derive(Clone, Copy, PartialEq, Eq, Debug, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Source {
    Env,
    Chosen,
    Checkout,
    Bundled,
}

/// Names that hold a person's own state; a sync never overwrites or removes these.
const KEEP: &[&str] = &[
    ".env",
    "config.env",
    ".lab-profile",
    ".sim-device",
    ".appium.pid",
    "storage",
    "shared",
    "backups",
    "oem",
    "artifacts",
    "apks",
    "frida",
    "__pycache__",
];

fn kept(name: &str) -> bool {
    KEEP.contains(&name)
}

/// Copy `src` over `dst`, file by file. Existing kept paths are left alone; nothing in `dst` is
/// deleted, so a lab's own files survive an update. Symlinks are skipped.
pub fn sync_tree(src: &Path, dst: &Path) -> io::Result<usize> {
    let mut copied = 0;
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let name = entry.file_name();
        let name_s = name.to_string_lossy();
        let target = dst.join(&name);
        let kind = entry.file_type()?;
        if kind.is_symlink() {
            continue;
        }
        if kept(&name_s) && target.exists() {
            continue;
        }
        if kind.is_dir() {
            copied += sync_tree(&entry.path(), &target)?;
        } else if kind.is_file() {
            let same = match (fs::metadata(entry.path()), fs::metadata(&target)) {
                (Ok(a), Ok(b)) => a.len() == b.len() && fs::read(entry.path())? == fs::read(&target)?,
                _ => false,
            };
            if !same {
                fs::copy(entry.path(), &target)?;
                copied += 1;
            }
        }
    }
    Ok(copied)
}

/// The dashboard build is replaced wholesale on an update: hashed assets from an older build
/// would otherwise pile up in the data folder.
pub fn sync_bundle(bundle: &Path, data_root: &Path, app_version: &str) -> Result<usize, String> {
    if !is_complete_bundle(bundle) {
        return Err(format!(
            "The bundled os-lab files are missing or incomplete ({}). Rebuild the app with `npm run stage`.",
            bundle.display()
        ));
    }
    let stamp = data_root.join(".app-version");
    let current = fs::read_to_string(&stamp).unwrap_or_default();
    if current.trim() == app_version && is_complete_bundle(data_root) {
        return Ok(0);
    }
    let dist = data_root.join("dashboard").join("dist");
    if dist.exists() {
        fs::remove_dir_all(&dist).map_err(|e| format!("Could not replace the old dashboard build: {e}"))?;
    }
    let copied = sync_tree(bundle, data_root).map_err(|e| format!("Could not prepare {}: {e}", data_root.display()))?;
    fs::write(&stamp, app_version).map_err(|e| format!("Could not write {}: {e}", stamp.display()))?;
    Ok(copied)
}

/// A development checkout: `app/src-tauri` → the repository two levels up.
pub fn dev_checkout() -> Option<PathBuf> {
    if !cfg!(debug_assertions) {
        return None;
    }
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent()?.parent()?.to_path_buf();
    is_root(&root).then_some(root)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> PathBuf {
        let p = std::env::temp_dir().join(format!("oslab-app-test-{}-{name}", std::process::id()));
        let _ = fs::remove_dir_all(&p);
        fs::create_dir_all(&p).unwrap();
        p
    }

    fn fake_root(dir: &Path, marker: &str) {
        fs::create_dir_all(dir.join("console")).unwrap();
        fs::create_dir_all(dir.join("android-lab/lab")).unwrap();
        fs::create_dir_all(dir.join("dashboard/dist")).unwrap();
        fs::write(dir.join("labctl"), "x").unwrap();
        fs::write(dir.join("console/oslab.py"), "x").unwrap();
        fs::write(dir.join("android-lab/lab/web_ui.py"), "x").unwrap();
        fs::write(dir.join("dashboard/dist/index.html"), marker).unwrap();
        for path in BUNDLE_FILES {
            let file = dir.join(path);
            fs::create_dir_all(file.parent().unwrap()).unwrap();
            if !file.exists() {
                fs::write(file, "x").unwrap();
            }
        }
    }

    #[test]
    fn root_needs_the_three_markers() {
        let d = tmp("markers");
        assert!(!is_root(&d));
        fake_root(&d, "a");
        assert!(is_root(&d));
    }

    #[test]
    fn sync_keeps_state_and_replaces_dashboard() {
        let bundle = tmp("bundle");
        let data = tmp("data");
        fake_root(&bundle, "v1");
        assert!(sync_bundle(&bundle, &data, "1").unwrap() > 0);
        // a person's state in the data folder
        fs::create_dir_all(data.join("android-lab/lab/storage")).unwrap();
        fs::write(data.join("android-lab/lab/storage/disk.img"), "mine").unwrap();
        fs::write(data.join("android-lab/lab/.env"), "SECRET=1").unwrap();
        fs::write(data.join("dashboard/dist/old-hash.js"), "old").unwrap();
        // same version: nothing to do
        assert_eq!(sync_bundle(&bundle, &data, "1").unwrap(), 0);
        // new version: new dashboard, old hashed asset gone, state untouched
        fs::write(bundle.join("dashboard/dist/index.html"), "v2").unwrap();
        fs::write(bundle.join("android-lab/lab/.env"), "SHOULD-NOT-OVERWRITE").unwrap();
        sync_bundle(&bundle, &data, "2").unwrap();
        assert_eq!(fs::read_to_string(data.join("dashboard/dist/index.html")).unwrap(), "v2");
        assert!(!data.join("dashboard/dist/old-hash.js").exists());
        assert_eq!(fs::read_to_string(data.join("android-lab/lab/.env")).unwrap(), "SECRET=1");
        assert_eq!(fs::read_to_string(data.join("android-lab/lab/storage/disk.img")).unwrap(), "mine");
    }

    #[test]
    fn incomplete_bundle_is_reported() {
        let bundle = tmp("empty");
        let data = tmp("data2");
        assert!(sync_bundle(&bundle, &data, "1").unwrap_err().contains("npm run stage"));
    }

    #[test]
    fn missing_installed_file_is_repaired_without_changing_state() {
        let bundle = tmp("repair-bundle");
        let data = tmp("repair-data");
        fake_root(&bundle, "v1");
        sync_bundle(&bundle, &data, "1").unwrap();
        fs::write(data.join("android-lab/lab/.env"), "SECRET=1").unwrap();
        fs::remove_file(data.join("docs/legal/PRIVACY.md")).unwrap();
        assert!(sync_bundle(&bundle, &data, "1").unwrap() > 0);
        assert!(data.join("docs/legal/PRIVACY.md").is_file());
        assert_eq!(fs::read_to_string(data.join("android-lab/lab/.env")).unwrap(), "SECRET=1");
    }
}

#[cfg(test)]
mod source_tests {
    use super::*;
    #[test]
    fn source_private_state_survives_tree_update() {
        let root = std::env::temp_dir().join(format!("oslab-source-sync-{}", std::process::id()));
        let source = root.join("bundle/source-lab");
        let target = root.join("data/source-lab");
        fs::create_dir_all(source.join("storage/control")).unwrap();
        fs::create_dir_all(target.join("storage/control")).unwrap();
        fs::write(source.join("run.py"), "new code").unwrap();
        fs::write(source.join("storage/control/runtime-settings.json"), "bundle").unwrap();
        fs::write(target.join("storage/control/runtime-settings.json"), "operator").unwrap();
        sync_tree(&source, &target).unwrap();
        assert_eq!(fs::read_to_string(target.join("run.py")).unwrap(), "new code");
        assert_eq!(fs::read_to_string(target.join("storage/control/runtime-settings.json")).unwrap(), "operator");
        fs::remove_dir_all(root).unwrap();
    }
}

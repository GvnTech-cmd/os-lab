//! Regenerable build folders among the current view's children, **proved by the
//! project around them** rather than guessed from the name.
//!
//! A folder called `target` is not necessarily a Rust build directory and a
//! folder called `venv` is not necessarily a virtualenv. A name only selects
//! which signatures to try; a candidate is reported when its project proves it:
//!
//! * `node_modules` next to a `package.json`;
//! * `target` next to a `Cargo.toml` (Rust) or a `pom.xml` (Maven);
//! * `.venv` / `venv` that contain a `pyvenv.cfg`;
//! * any directory with a valid `CACHEDIR.TAG` (<https://bford.info/cachedir/>).
//!
//! The table mirrors `cleanup-lab/reference/python/cleanup_ref/artifacts.py`
//! (same ids, names and markers) so both engines give the same answer; keep the
//! two in step. Read-only: `symlink_metadata` and a bounded read of the tag.

use std::fs;
use std::io::Read;
use std::path::Path;

use crate::tree::{NodeId, Tree};

const CACHEDIR_TAG: &str = "CACHEDIR.TAG";
const CACHEDIR_SIGNATURE: &[u8] = b"Signature: 8a477f597d28d172789f06886806bc55";

/// One kind of regenerable project artifact.
#[derive(Debug)]
pub struct Signature {
    pub id: &'static str,
    pub names: &'static [&'static str],
    pub ecosystem: &'static str,
    pub regenerate: &'static str,
    /// At least one must exist in the parent directory (the project).
    pub sibling_markers: &'static [&'static str],
    /// At least one must exist inside the matched directory.
    pub inner_markers: &'static [&'static str],
}

const fn sig(
    id: &'static str,
    names: &'static [&'static str],
    ecosystem: &'static str,
    regenerate: &'static str,
    sibling_markers: &'static [&'static str],
    inner_markers: &'static [&'static str],
) -> Signature {
    Signature {
        id,
        names,
        ecosystem,
        regenerate,
        sibling_markers,
        inner_markers,
    }
}

pub const SIGNATURES: &[Signature] = &[
    sig(
        "node_modules",
        &["node_modules"],
        "Node.js",
        "npm / pnpm / yarn / bun install",
        &["package.json"],
        &[],
    ),
    sig(
        "rust_target",
        &["target"],
        "Rust",
        "cargo build",
        &["Cargo.toml"],
        &[],
    ),
    sig(
        "maven_target",
        &["target"],
        "Java (Maven)",
        "mvn package",
        &["pom.xml"],
        &[],
    ),
    sig(
        "gradle_project_cache",
        &[".gradle"],
        "Java/Kotlin (Gradle)",
        "gradle build",
        &[
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "settings.gradle.kts",
        ],
        &[],
    ),
    sig(
        "gradle_build",
        &["build"],
        "Java/Kotlin (Gradle)",
        "gradle build",
        &["build.gradle", "build.gradle.kts"],
        &[],
    ),
    sig(
        "python_venv",
        &[".venv", "venv"],
        "Python",
        "python -m venv + pip install -r …",
        &[],
        &["pyvenv.cfg"],
    ),
    sig(
        "python_tox",
        &[".tox"],
        "Python",
        "tox",
        &["tox.ini", "pyproject.toml", "setup.cfg"],
        &[],
    ),
    sig(
        "python_pycache",
        &["__pycache__"],
        "Python",
        "regenerated on import",
        &[],
        &[],
    ),
    sig(
        "next_build",
        &[".next"],
        "Next.js",
        "next build",
        &["package.json"],
        &[],
    ),
    sig(
        "nuxt_build",
        &[".nuxt", ".output"],
        "Nuxt",
        "nuxt build",
        &["nuxt.config.ts", "nuxt.config.js"],
        &[],
    ),
    sig(
        "svelte_kit",
        &[".svelte-kit"],
        "SvelteKit",
        "vite build",
        &["svelte.config.js", "svelte.config.ts"],
        &[],
    ),
    sig(
        "js_tool_cache",
        &[".turbo", ".parcel-cache", ".angular"],
        "JavaScript tooling",
        "rebuilt by the next build",
        &["package.json"],
        &[],
    ),
    sig(
        "dart_tool",
        &[".dart_tool"],
        "Dart/Flutter",
        "dart pub get",
        &["pubspec.yaml"],
        &[],
    ),
    sig(
        "swiftpm_build",
        &[".build"],
        "Swift Package Manager",
        "swift build",
        &["Package.swift"],
        &[],
    ),
    sig(
        "zig_cache",
        &["zig-cache", ".zig-cache", "zig-out"],
        "Zig",
        "zig build",
        &["build.zig"],
        &[],
    ),
    sig(
        "elixir_build",
        &["_build", "deps"],
        "Elixir",
        "mix deps.get && mix compile",
        &["mix.exs"],
        &[],
    ),
    sig(
        "terraform_providers",
        &[".terraform"],
        "Terraform",
        "terraform init",
        &["main.tf", "versions.tf", "terraform.tf"],
        &[],
    ),
];

/// Reported when a folder carries a valid `CACHEDIR.TAG` but matches no named signature.
pub const CACHEDIR_TAGGED: Signature = sig(
    "cachedir_tag",
    &[],
    "Any (CACHEDIR.TAG)",
    "tool that wrote the tag regenerates it",
    &[],
    &[],
);

/// A verified candidate in the current view.
#[derive(Debug)]
pub struct Candidate {
    pub node: NodeId,
    pub signature_id: &'static str,
    pub ecosystem: &'static str,
    pub regenerate: &'static str,
}

fn exists_no_follow(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok()
}

/// True when `dir/CACHEDIR.TAG` is a regular file that starts with the spec signature.
pub fn has_cachedir_tag(dir: &Path) -> bool {
    let tag = dir.join(CACHEDIR_TAG);
    let Ok(meta) = fs::symlink_metadata(&tag) else {
        return false;
    };
    if !meta.is_file() {
        return false;
    }
    let mut buf = vec![0u8; CACHEDIR_SIGNATURE.len()];
    fs::File::open(&tag)
        .and_then(|mut f| f.read_exact(&mut buf))
        .is_ok()
        && buf == CACHEDIR_SIGNATURE
}

/// The signature that the real directory `dir` proves, if any. `dir` must be a
/// real directory, not a symlink; `parent` is its containing directory.
pub fn classify_dir(parent: &Path, name: &str) -> Option<&'static Signature> {
    let dir = parent.join(name);
    if !fs::symlink_metadata(&dir).ok()?.is_dir() {
        return None;
    }
    for s in SIGNATURES.iter().filter(|s| s.names.contains(&name)) {
        let marked = (s.sibling_markers.is_empty() && s.inner_markers.is_empty())
            || s.sibling_markers
                .iter()
                .any(|m| exists_no_follow(&parent.join(m)))
            || s.inner_markers
                .iter()
                .any(|m| exists_no_follow(&dir.join(m)));
        if marked {
            return Some(s);
        }
    }
    has_cachedir_tag(&dir).then_some(&CACHEDIR_TAGGED)
}

/// Visible children of `view_root` that their project proves are regenerable.
/// `view_root_abs_path` is the real filesystem path of `view_root`. Only the
/// current view is examined, like the gitignore view.
pub fn cleanup_candidates(
    tree: &Tree,
    view_root: NodeId,
    view_root_abs_path: &Path,
) -> Vec<Candidate> {
    tree.children(view_root)
        .into_iter()
        .filter_map(|id| {
            let n = &tree.nodes[id as usize];
            if !n.is_dir {
                return None;
            }
            let s = classify_dir(view_root_abs_path, &n.name)?;
            Some(Candidate {
                node: id,
                signature_id: s.id,
                ecosystem: s.ecosystem,
                regenerate: s.regenerate,
            })
        })
        .collect()
}

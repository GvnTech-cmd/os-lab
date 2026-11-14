//! qrust-scan — a cross-platform disk-usage scan engine, vendored into os-lab
//! Cleanup Lab as a reference backend (see `cleanup-lab/reference/README.md`).
//!
//! A reimplementation of dua-cli's scan/seek *algorithms* (not a fork of dua's
//! source): a parallel `jwalk` directory walk with allocated-size-on-disk
//! measurement, hard-link de-duplication, and a single-pass depth-stack rollup
//! into a parent-summed size tree.
//!
//! - [`walk`] — the parallel walk and its rollup (§2, §3.2).
//! - [`tree`] — the resulting tree: sibling sort modes and the greedy
//!   size-descending "hotspot" descend used to find disk hogs (§10.1, §10.6).
//! - [`glob_search`] — in-memory DFS glob seek over an already-scanned tree,
//!   pruning at each match (§10.2).
//! - [`cleanup`] — regenerable build folders in the current view, each proved by
//!   a marker file in its project (`node_modules` + `package.json`, `target` +
//!   `Cargo.toml`, `.venv` + `pyvenv.cfg`, a valid `CACHEDIR.TAG`, …) (§10.3).
//! - [`gitignore`] — repo discovery and git's ignore stack (global excludes,
//!   `info/exclude`, nested `.gitignore` files) for the current view (§10.4).
//! - [`platform`] — the only OS-specific part: allocated size, file identity and
//!   the default thread count.
//!
//! Everything is read-only: the engine measures and searches, it never deletes.
//! Cleanup decisions go through os-lab's plan → confirm → clean flow (CLN-13).

pub mod cancel;
pub mod cleanup;
pub mod gitignore;
pub mod glob_search;
pub mod platform;
pub mod tree;
pub mod walk;

pub use cancel::CancelFlag;
pub use cleanup::{classify_dir, cleanup_candidates, Candidate, Signature, SIGNATURES};
pub use gitignore::{discover_repo_root, gitignored_children, gitignored_children_with};
pub use glob_search::{glob_search, GlobMatch};
pub use platform::{default_threads, EntryFacts};
pub use tree::{Node, NodeId, SortMode, Tree, NO_ID};
pub use walk::{scan, scan_cancellable, scan_with_progress, ScanError, ScanOptions};

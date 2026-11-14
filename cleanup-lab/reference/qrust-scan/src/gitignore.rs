//! Which entries of the current view git would ignore.
//!
//! Follows git's precedence, lowest first: the global excludes file
//! (`core.excludesFile`), `$GIT_DIR/info/exclude`, then the `.gitignore` of the
//! repository root and of every directory on the way down to the entry. A deeper
//! file overrides a shallower one, and git cannot re-include anything below a
//! directory that is itself ignored, so that is checked too.
//!
//! Read-only: only the ignore files are opened, nothing is written.

use std::fs;
use std::path::{Path, PathBuf};

use ignore::gitignore::{Gitignore, GitignoreBuilder};
use ignore::Match;

use crate::tree::{NodeId, Tree};

/// Walk upward from `start` looking for a `.git` entry (a directory, or a file
/// in a worktree or submodule).
pub fn discover_repo_root(start: &Path) -> Option<PathBuf> {
    let mut cur = Some(start);
    while let Some(dir) = cur {
        if dir.join(".git").exists() {
            return Some(dir.to_path_buf());
        }
        cur = dir.parent();
    }
    None
}

/// The directory holding `info/exclude` for the repository at `repo_root`.
/// `.git` is a directory in a normal clone; in a worktree or submodule it is a
/// file `gitdir: <path>`, and the shared `info/` lives in `commondir`.
fn git_info_dir(repo_root: &Path) -> Option<PathBuf> {
    let dot_git = repo_root.join(".git");
    let git_dir = if dot_git.is_dir() {
        dot_git
    } else {
        let text = fs::read_to_string(&dot_git).ok()?;
        let target = text.lines().find_map(|l| l.strip_prefix("gitdir:"))?.trim();
        let target = Path::new(target);
        if target.is_absolute() {
            target.to_path_buf()
        } else {
            repo_root.join(target)
        }
    };
    let common = fs::read_to_string(git_dir.join("commondir")).ok().map(|c| {
        let c = c.trim();
        let c = Path::new(c);
        if c.is_absolute() {
            c.to_path_buf()
        } else {
            git_dir.join(c)
        }
    });
    Some(common.unwrap_or(git_dir).join("info"))
}

fn file_matcher(base: &Path, file: &Path) -> Option<Gitignore> {
    if !file.is_file() {
        return None;
    }
    let mut b = GitignoreBuilder::new(base);
    // A malformed line is skipped by the builder; an unreadable file is just absent.
    let _ = b.add(file);
    b.build().ok()
}

/// Matchers that apply to entries directly inside `dir`, lowest precedence first.
fn matcher_stack(repo_root: &Path, dir: &Path) -> Vec<Gitignore> {
    let mut stack = Vec::new();
    if let Some(info) = git_info_dir(repo_root) {
        if let Some(m) = file_matcher(repo_root, &info.join("exclude")) {
            stack.push(m);
        }
    }
    let rel = dir
        .strip_prefix(repo_root)
        .unwrap_or_else(|_| Path::new(""));
    let mut cur = repo_root.to_path_buf();
    if let Some(m) = file_matcher(&cur, &cur.join(".gitignore")) {
        stack.push(m);
    }
    for part in rel.components() {
        cur.push(part);
        if let Some(m) = file_matcher(&cur, &cur.join(".gitignore")) {
            stack.push(m);
        }
    }
    stack
}

/// Highest-precedence matcher with an opinion wins.
fn decide(stack: &[Gitignore], path: &Path, is_dir: bool) -> Option<bool> {
    for m in stack.iter().rev() {
        match m.matched(path, is_dir) {
            Match::Ignore(_) => return Some(true),
            Match::Whitelist(_) => return Some(false),
            Match::None => {}
        }
    }
    None
}

/// Visible children of `view_root` that git would ignore. `view_root_abs_path`
/// is the real filesystem path of `view_root` (the tree only stores names). The
/// global excludes file comes from the user's git config (`core.excludesFile`,
/// else `$XDG_CONFIG_HOME/git/ignore`).
pub fn gitignored_children(
    tree: &Tree,
    view_root: NodeId,
    view_root_abs_path: &Path,
) -> Vec<NodeId> {
    let global = Gitignore::global().0;
    gitignored_children_impl(tree, view_root, view_root_abs_path, Some(&global))
}

/// Like [`gitignored_children`], with the global excludes file given explicitly
/// (or `None` for no global file) so the result does not depend on the machine.
pub fn gitignored_children_with(
    tree: &Tree,
    view_root: NodeId,
    view_root_abs_path: &Path,
    global_excludes: Option<&Path>,
) -> Vec<NodeId> {
    let global = global_excludes.and_then(|p| {
        let mut b = GitignoreBuilder::new(Path::new("/"));
        let _ = b.add(p);
        b.build().ok()
    });
    gitignored_children_impl(tree, view_root, view_root_abs_path, global.as_ref())
}

fn gitignored_children_impl(
    tree: &Tree,
    view_root: NodeId,
    view_root_abs_path: &Path,
    global: Option<&Gitignore>,
) -> Vec<NodeId> {
    let Some(repo_root) = discover_repo_root(view_root_abs_path) else {
        return Vec::new();
    };
    let mut stack = matcher_stack(&repo_root, view_root_abs_path);
    if let Some(g) = global {
        stack.insert(0, g.clone());
    }

    // If the view itself sits inside an ignored directory, everything in it is ignored.
    let inside_ignored = view_ancestors_ignored(&repo_root, view_root_abs_path, global);

    tree.children(view_root)
        .into_iter()
        .filter(|&id| {
            let n = &tree.nodes[id as usize];
            let full = view_root_abs_path.join(n.name.as_ref());
            inside_ignored || decide(&stack, &full, n.is_dir) == Some(true)
        })
        .collect()
}

/// True when any directory from the repo root down to `view` (inclusive) is ignored.
fn view_ancestors_ignored(repo_root: &Path, view: &Path, global: Option<&Gitignore>) -> bool {
    let Ok(rel) = view.strip_prefix(repo_root) else {
        return false;
    };
    let mut cur = repo_root.to_path_buf();
    for part in rel.components() {
        let mut stack = matcher_stack(repo_root, &cur);
        if let Some(g) = global {
            stack.insert(0, g.clone());
        }
        cur.push(part);
        if decide(&stack, &cur, true) == Some(true) {
            return true;
        }
    }
    false
}

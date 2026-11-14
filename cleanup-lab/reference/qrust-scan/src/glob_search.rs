use globset::GlobBuilder;

use crate::tree::{NodeId, Tree};

#[derive(Debug)]
pub struct GlobMatch {
    pub node: NodeId,
    pub relative_path: String,
}

/// In-memory glob seek over an already-scanned tree — dua's `/` search.
/// Scoped to the subtree under `view_root`, not a filesystem re-walk. `*`/`?`
/// never cross `/` (dua's `NO_MATCH_SLASH_LITERAL`); `**` still crosses
/// directory boundaries. On a match the node is recorded and its children are
/// *not* searched further — the match is the seek result.
///
/// Iterative (an explicit stack of sibling lists), so a tree of any depth
/// cannot overflow the call stack. Results are in the same pre-order as the
/// recursive version this replaced.
pub fn glob_search(
    tree: &Tree,
    view_root: NodeId,
    pattern: &str,
    case_insensitive: bool,
) -> Result<Vec<GlobMatch>, String> {
    let trimmed = pattern.trim();
    if trimmed.is_empty() {
        return Err("Glob was empty or only whitespace".to_string());
    }
    let glob = GlobBuilder::new(trimmed)
        .case_insensitive(case_insensitive)
        .literal_separator(true)
        .build()
        .map_err(|e| e.to_string())?
        .compile_matcher();

    struct Frame {
        kids: Vec<NodeId>,
        next: usize,
        /// Length of `path` for this frame's parent.
        prefix_len: usize,
    }

    let mut results = Vec::new();
    let mut path = String::new();
    let mut stack = vec![Frame {
        kids: tree.children(view_root),
        next: 0,
        prefix_len: 0,
    }];
    while let Some(frame) = stack.last_mut() {
        let Some(&child) = frame.kids.get(frame.next) else {
            stack.pop();
            continue;
        };
        frame.next += 1;
        path.truncate(frame.prefix_len);
        let n = &tree.nodes[child as usize];
        if !path.is_empty() {
            path.push('/');
        }
        path.push_str(&n.name);

        if glob.is_match(path.as_str()) {
            results.push(GlobMatch {
                node: child,
                relative_path: path.clone(),
            });
        } else if n.is_dir {
            let prefix_len = path.len();
            stack.push(Frame {
                kids: tree.children(child),
                next: 0,
                prefix_len,
            });
        }
    }
    Ok(results)
}

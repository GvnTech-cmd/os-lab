use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

use jwalk::{Parallelism, WalkDirGeneric};
use rayon::ThreadPoolBuilder;

use crate::cancel::CancelFlag;
use crate::platform::{self, EntryFacts};
use crate::tree::{Node, NodeId, Tree, NO_ID};

/// Why a cancellable scan stopped short of a full tree. Kept distinct from a
/// plain `io::Error` so a caller can report cancellation as its own status
/// rather than a generic scan failure.
#[derive(Debug)]
pub enum ScanError {
    /// An I/O failure setting up or driving the walk.
    Io(std::io::Error),
    /// The caller's `CancelFlag` was tripped during traversal or aggregation.
    Cancelled,
}

impl std::fmt::Display for ScanError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ScanError::Io(e) => write!(f, "{e}"),
            ScanError::Cancelled => write!(f, "scan cancelled"),
        }
    }
}

impl std::error::Error for ScanError {}

impl From<std::io::Error> for ScanError {
    fn from(e: std::io::Error) -> Self {
        ScanError::Io(e)
    }
}

/// Per-entry state captured once inside jwalk's `process_read_dir` callback, on
/// a parallel worker, mirroring dua's "metadata fetched in the walk callback,
/// stored as client_state" design.
#[derive(Debug, Clone, Default)]
struct EntryMeta {
    facts: EntryFacts,
    /// The entry's metadata could not be read; counted as an I/O error.
    error: bool,
}

#[derive(Debug, Clone)]
pub struct ScanOptions {
    pub root: PathBuf,
    /// 0 => the platform default: 3 on Apple platforms, else the machine's
    /// parallelism (capped). `dua -t`.
    pub threads: usize,
    /// `dua -A` / `--apparent-size`: use logical length instead of allocated blocks.
    pub apparent_size: bool,
    /// `dua -x` / `--stay-on-filesystem`.
    pub stay_on_filesystem: bool,
    /// `dua -l` / `--count-hard-links`: disable hard-link de-duplication.
    pub count_hard_links: bool,
}

impl ScanOptions {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self {
            root: root.into(),
            threads: 0,
            apparent_size: false,
            stay_on_filesystem: false,
            count_hard_links: false,
        }
    }

    pub fn resolved_threads(&self) -> usize {
        if self.threads == 0 {
            platform::default_threads()
        } else {
            self.threads
        }
    }
}

/// Run a parallel scan of `opts.root` and return the resulting size tree.
///
/// Mirrors dua's pipeline: `jwalk` parallel walk with a custom
/// Rayon pool, allocated-size-on-disk measurement, hard-link de-duplication by
/// `(dev, inode)` — or `(volume, file index)` on Windows — and a single-pass
/// depth-stack rollup that sums child sizes and counts into their parent as the
/// walk streams in strict depth-first order, so no second pass over the tree is
/// needed.
pub fn scan(opts: &ScanOptions) -> std::io::Result<Tree> {
    scan_with_progress(opts, None)
}

/// Throttled interval between `on_progress` calls — frequent enough to feel
/// live, infrequent enough that reporting overhead is negligible next to the
/// I/O the walk itself does.
/// Progress callback: `(processed_entries, total_bytes_seen_so_far, current_path)`.
pub type ProgressFn<'a> = &'a mut dyn FnMut(u64, u64, &str);

const PROGRESS_REPORT_INTERVAL: Duration = Duration::from_millis(120);

/// Same as [`scan`], but invokes `on_progress(processed_entries,
/// total_bytes_seen_so_far, current_path)` while the walk is in flight. A
/// convenience for callers that want progress but not cancellation; there is no
/// cancel flag, so `ScanError::Cancelled` cannot occur.
pub fn scan_with_progress(
    opts: &ScanOptions,
    on_progress: Option<ProgressFn<'_>>,
) -> std::io::Result<Tree> {
    match scan_cancellable(opts, on_progress, None) {
        Ok(tree) => Ok(tree),
        Err(ScanError::Io(e)) => Err(e),
        Err(ScanError::Cancelled) => {
            unreachable!("scan_with_progress passes no CancelFlag, so cancellation cannot occur")
        }
    }
}

/// The scan core. Invokes `on_progress(processed_entries,
/// total_bytes_seen_so_far, current_path)` on the first processed entry, then at
/// [`PROGRESS_REPORT_INTERVAL`] while the walk is in flight, plus once more with
/// the final totals (empty path) when it finishes. Called only from the thread
/// driving the `for item in walker` loop below (jwalk's pool threads never see
/// it), so no `Send` bound is needed on the closure.
///
/// If `cancel` is supplied, the flag is polled at the top of every walk
/// iteration and before every trailing rollup step; once it is set, the scan
/// abandons the partial tree and returns [`ScanError::Cancelled`] instead of
/// running to completion.
pub fn scan_cancellable(
    opts: &ScanOptions,
    mut on_progress: Option<ProgressFn<'_>>,
    cancel: Option<&CancelFlag>,
) -> Result<Tree, ScanError> {
    let started_at = Instant::now();
    let root_meta = std::fs::symlink_metadata(&opts.root)?;
    let root_facts = EntryFacts::new(&opts.root, &root_meta);
    let root_dev = root_facts.dev;

    let threads = opts.resolved_threads();
    let pool = Arc::new(build_pool(threads, WALK_THREAD_STACK)?);

    let stay_on_filesystem = opts.stay_on_filesystem;

    let walker = WalkDirGeneric::<((), EntryMeta)>::new(&opts.root)
        .skip_hidden(false)
        .follow_links(false)
        .parallelism(if threads <= 1 {
            Parallelism::Serial
        } else {
            Parallelism::RayonExistingPool {
                pool: pool.clone(),
                busy_timeout: None,
            }
        })
        .process_read_dir(move |_depth, _path, _read_dir_state, children| {
            for child in children.iter_mut() {
                let Ok(entry) = child else { continue };
                match entry.metadata() {
                    Ok(meta) => {
                        let facts = EntryFacts::new(entry.path().as_path(), &meta);
                        if stay_on_filesystem && facts.is_dir && facts.dev != root_dev {
                            // Don't descend into other devices/mounts (dua's `-x`).
                            entry.read_children_path = None;
                        }
                        entry.client_state = EntryMeta {
                            facts,
                            error: false,
                        };
                    }
                    Err(_) => {
                        entry.client_state = EntryMeta {
                            error: true,
                            ..Default::default()
                        };
                    }
                }
            }
        });

    let mut nodes: Vec<Node> = vec![Node::new_dir(root_name(&opts.root), root_facts.mtime)];
    let mut io_errors: u32 = 0;
    let mut seen_links: HashMap<(u64, u64), u32> = HashMap::new();
    let mut stack: Vec<NodeId> = vec![0];
    let mut processed: u64 = 0;
    let mut bytes_seen: u64 = 0;
    let mut last_report = Instant::now();

    for item in walker {
        // Traversal cancellation checkpoint: polled once per streamed entry so a
        // cancel from another thread stops us within one entry instead of
        // building the whole tree.
        if cancel.is_some_and(CancelFlag::is_cancelled) {
            return Err(ScanError::Cancelled);
        }
        let entry = match item {
            Ok(e) => e,
            Err(_) => {
                io_errors += 1;
                if let Some(&top) = stack.last() {
                    nodes[top as usize].has_error = true;
                }
                continue;
            }
        };

        let depth = entry.depth;
        if depth == 0 {
            // The root itself — already represented by node 0.
            continue;
        }
        while stack.len() > depth {
            finalize(&mut nodes, &mut stack);
        }
        let parent_id = *stack.last().expect("scan stack must contain the root");
        let meta = entry.client_state.clone();
        let facts = meta.facts;

        let mut contributed_size = facts.size(opts.apparent_size);
        if facts.is_dir {
            contributed_size = 0; // rolled up when this dir is finalized
        } else if stay_on_filesystem && facts.dev != root_dev {
            contributed_size = 0; // "same-device check"
        } else if !opts.count_hard_links && facts.nlink > 1 {
            let seen = seen_links.entry((facts.dev, facts.ino)).or_insert(0);
            if *seen > 0 {
                contributed_size = 0; // later sighting of an already-counted hard link
            }
            *seen += 1;
        }
        if meta.error {
            io_errors += 1;
        }

        // `NO_ID` (u32::MAX) is the "none" marker, so ids must stay below it.
        let node_id = NodeId::try_from(nodes.len())
            .ok()
            .filter(|&id| id != NO_ID)
            .ok_or_else(|| {
                ScanError::Io(std::io::Error::other(
                    "the tree has more entries than one scan can index",
                ))
            })?;
        nodes.push(Node {
            name: entry
                .file_name
                .to_string_lossy()
                .into_owned()
                .into_boxed_str(),
            parent: parent_id,
            first_child: NO_ID,
            next_sibling: NO_ID,
            size: contributed_size,
            entry_count: 1,
            mtime: facts.mtime,
            max_mtime: facts.mtime,
            is_dir: facts.is_dir,
            has_error: meta.error,
        });

        nodes[node_id as usize].next_sibling = nodes[parent_id as usize].first_child;
        nodes[parent_id as usize].first_child = node_id;

        if !facts.is_dir {
            let p = &mut nodes[parent_id as usize];
            p.size += contributed_size;
            p.entry_count = p.entry_count.saturating_add(1);
            p.max_mtime = p.max_mtime.max(facts.mtime);
        }

        if facts.is_dir {
            stack.push(node_id);
        }

        processed += 1;
        bytes_seen += contributed_size;
        if let Some(cb) = on_progress.as_mut() {
            // Fire on the very first entry so callers get an immediate tick,
            // then throttle to PROGRESS_REPORT_INTERVAL thereafter.
            if processed == 1 || last_report.elapsed() >= PROGRESS_REPORT_INTERVAL {
                cb(processed, bytes_seen, &entry.path().to_string_lossy());
                last_report = Instant::now();
            }
        }
    }
    while stack.len() > 1 {
        // Aggregation cancellation checkpoint: the trailing rollup is cheap
        // (bounded by tree depth) but polled anyway, so a cancel arriving as the
        // walk finishes is still honored rather than ignored.
        if cancel.is_some_and(CancelFlag::is_cancelled) {
            return Err(ScanError::Cancelled);
        }
        finalize(&mut nodes, &mut stack);
    }
    if let Some(cb) = on_progress.as_mut() {
        cb(processed, bytes_seen, "");
    }

    Ok(Tree {
        nodes,
        root: 0,
        io_errors,
        elapsed: started_at.elapsed(),
    })
}

const WALK_THREAD_STACK: usize = 128 * 1024;

/// The walk's dedicated Rayon pool. Failing to create it (no threads left, no
/// memory for the stacks) is an ordinary scan error for the caller to report,
/// never a panic inside an app that is otherwise healthy.
fn build_pool(threads: usize, stack_size: usize) -> Result<rayon::ThreadPool, ScanError> {
    ThreadPoolBuilder::new()
        .num_threads(threads.max(1))
        .stack_size(stack_size)
        .thread_name(|i| format!("qrust-scan-walk-{i}"))
        .build()
        .map_err(|e| {
            ScanError::Io(std::io::Error::other(format!(
                "could not start the scan thread pool: {e}"
            )))
        })
}

/// Roll a finished directory's totals up into its parent — the "depth decreases
/// → finalize parent node sizes/counts, pop stack" step from dua's
/// `BackgroundTraversal`.
fn finalize(nodes: &mut [Node], stack: &mut Vec<NodeId>) {
    let popped = stack
        .pop()
        .expect("qrust-scan: stack underflow during finalize");
    if let Some(&parent_id) = stack.last() {
        let (size, count, mtime, has_error) = {
            let n = &nodes[popped as usize];
            (n.size, n.entry_count, n.max_mtime, n.has_error)
        };
        let p = &mut nodes[parent_id as usize];
        p.size += size;
        p.entry_count = p.entry_count.saturating_add(count);
        p.max_mtime = p.max_mtime.max(mtime);
        p.has_error = p.has_error || has_error;
    }
}

fn root_name(path: &Path) -> String {
    path.file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| path.to_string_lossy().into_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dir(count: u32) -> Node {
        let mut n = Node::new_dir("d".into(), 0);
        n.entry_count = count;
        n
    }

    #[test]
    fn pool_failure_is_an_error_not_a_panic() {
        // A stack this large cannot be mapped, so the pool cannot start its workers.
        let err = build_pool(2, usize::MAX / 2).expect_err("pool must not build");
        assert!(matches!(err, ScanError::Io(_)));
        assert!(err.to_string().contains("thread pool"));
    }

    #[test]
    fn entry_count_saturates_instead_of_wrapping() {
        let mut nodes = vec![dir(u32::MAX - 1), dir(5)];
        nodes[1].parent = 0;
        let mut stack = vec![0, 1];
        finalize(&mut nodes, &mut stack);
        assert_eq!(nodes[0].entry_count, u32::MAX);
    }
}

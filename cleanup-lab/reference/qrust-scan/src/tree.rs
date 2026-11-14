use std::time::Duration;

pub type NodeId = u32;
pub const NO_ID: NodeId = u32::MAX;

/// Sort orders exposed by dua's interactive entry list (`SortMode` +
/// the mtime cycle). Applies to `Tree::children_sorted`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SortMode {
    SizeDescending,
    SizeAscending,
    Name,
    Count,
    MtimeNewest,
    MtimeOldest,
}

/// One entry in the scan tree. Kept small and `Copy`-free but flat
/// (parent + linked-list children) rather than a boxed graph, mirroring
/// dua's goal of a compact `EntryData` for large trees.
#[derive(Debug)]
pub struct Node {
    pub name: Box<str>,
    pub parent: NodeId,
    pub first_child: NodeId,
    pub next_sibling: NodeId,
    /// Recursive size in bytes (allocated-on-disk or apparent, per `ScanOptions::apparent_size`).
    /// For files this is the file's own contribution; for directories it is the rollup of children.
    pub size: u64,
    /// Recursive entry count, including this node itself.
    pub entry_count: u32,
    /// This node's own filesystem mtime (unix seconds).
    pub mtime: i64,
    /// Max mtime across this node and all descendants (for "recursive newest" sort).
    pub max_mtime: i64,
    pub is_dir: bool,
    pub has_error: bool,
}

impl Node {
    pub(crate) fn new_dir(name: String, mtime: i64) -> Self {
        Node {
            name: name.into_boxed_str(),
            parent: NO_ID,
            first_child: NO_ID,
            next_sibling: NO_ID,
            size: 0,
            entry_count: 1,
            mtime,
            max_mtime: mtime,
            is_dir: true,
            has_error: false,
        }
    }
}

pub struct Tree {
    pub nodes: Vec<Node>,
    pub root: NodeId,
    /// Count of read/stat failures encountered during the walk (permission
    /// denials, vanished entries, etc.) — dua counts these as IO errors.
    pub io_errors: u32,
    pub elapsed: Duration,
}

impl Tree {
    pub fn children(&self, id: NodeId) -> Vec<NodeId> {
        let mut out = Vec::new();
        let mut cur = self.nodes[id as usize].first_child;
        while cur != NO_ID {
            out.push(cur);
            cur = self.nodes[cur as usize].next_sibling;
        }
        out
    }

    pub fn children_sorted(&self, id: NodeId, mode: SortMode) -> Vec<NodeId> {
        let mut kids = self.children(id);
        kids.sort_by(|&a, &b| {
            let (na, nb) = (&self.nodes[a as usize], &self.nodes[b as usize]);
            match mode {
                SortMode::SizeDescending => nb.size.cmp(&na.size),
                SortMode::SizeAscending => na.size.cmp(&nb.size),
                SortMode::Name => na.name.cmp(&nb.name),
                SortMode::Count => nb.entry_count.cmp(&na.entry_count),
                SortMode::MtimeNewest => nb.max_mtime.cmp(&na.max_mtime),
                SortMode::MtimeOldest => na.max_mtime.cmp(&nb.max_mtime),
            }
        });
        kids
    }

    /// `Traversal::is_costly()` in dua: true once a scan has taken more than 10s.
    pub fn is_costly(&self) -> bool {
        self.elapsed.as_secs_f64() > 10.0
    }

    /// Slash-joined path from the scan root down to `id` (root's own name is the first segment).
    pub fn path_of(&self, mut id: NodeId) -> String {
        let mut parts: Vec<&str> = Vec::new();
        loop {
            let n = &self.nodes[id as usize];
            parts.push(n.name.as_ref());
            if id == self.root {
                break;
            }
            id = n.parent;
        }
        parts.reverse();
        parts.join("/")
    }

    /// Greedy size-descending descend from `id` to a leaf — the manual
    /// "hotspot seek" dua's UI performs when you always open the top row
    ///.
    pub fn hotspot_descend(&self, start: NodeId) -> Vec<NodeId> {
        let mut path = vec![start];
        let mut id = start;
        loop {
            let kids = self.children_sorted(id, SortMode::SizeDescending);
            match kids.first() {
                Some(&next) => {
                    path.push(next);
                    if self.nodes[next as usize].is_dir && !self.children(next).is_empty() {
                        id = next;
                    } else {
                        break;
                    }
                }
                None => break,
            }
        }
        path
    }
}

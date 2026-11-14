use std::fs;
use std::io::Write;
use std::path::Path;

use qrust_scan::walk::scan_with_progress;
use qrust_scan::{
    cleanup_candidates, gitignored_children, glob_search, scan, scan_cancellable, CancelFlag,
    ScanError, ScanOptions, SortMode,
};

fn write_file(path: &Path, bytes: usize) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    let mut f = fs::File::create(path).unwrap();
    f.write_all(&vec![b'x'; bytes]).unwrap();
}

fn tmp_root(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("qrust-scan-test-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn rollup_sums_children_into_parent() {
    let root = tmp_root("rollup");
    write_file(&root.join("a.txt"), 4096);
    write_file(&root.join("sub/b.txt"), 4096);
    write_file(&root.join("sub/deeper/c.txt"), 4096);

    let opts = ScanOptions::new(&root);
    let tree = scan(&opts).expect("scan should succeed");

    let root_id = tree.root;
    assert!(
        tree.nodes[root_id as usize].size > 0,
        "root should roll up all descendant sizes"
    );
    assert_eq!(
        tree.nodes[root_id as usize].entry_count, 6,
        "root + a.txt + sub + sub/b.txt + sub/deeper + sub/deeper/c.txt"
    );

    let kids = tree.children_sorted(root_id, SortMode::Name);
    let names: Vec<&str> = kids
        .iter()
        .map(|&id| tree.nodes[id as usize].name.as_ref())
        .collect();
    assert_eq!(names, vec!["a.txt", "sub"]);

    let sub_id = kids[1];
    assert!(tree.nodes[sub_id as usize].is_dir);
    // sub's rolled-up size must be >= its two descendant files' allocated bytes.
    assert!(tree.nodes[sub_id as usize].size >= tree.nodes[root_id as usize].size / 3);

    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn hotspot_descend_reaches_the_biggest_leaf() {
    let root = tmp_root("hotspot");
    write_file(&root.join("small.txt"), 100);
    write_file(&root.join("big/payload.bin"), 200_000);

    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let path = tree.hotspot_descend(tree.root);
    let last = *path.last().unwrap();
    assert_eq!(tree.nodes[last as usize].name.as_ref(), "payload.bin");

    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn hard_links_are_only_counted_once() {
    let root = tmp_root("hardlink");
    write_file(&root.join("original.bin"), 100_000);
    fs::hard_link(root.join("original.bin"), root.join("linked.bin")).unwrap();

    let deduped = scan(&ScanOptions::new(&root)).unwrap();
    let mut opts_counted = ScanOptions::new(&root);
    opts_counted.count_hard_links = true;
    let counted = scan(&opts_counted).unwrap();

    assert!(
        counted.nodes[counted.root as usize].size > deduped.nodes[deduped.root as usize].size,
        "counting hard links twice must produce a larger total than de-duplicated"
    );

    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn glob_search_prunes_at_first_match() {
    let root = tmp_root("glob");
    write_file(&root.join("proj/node_modules/pkg/index.js"), 10);
    write_file(&root.join("proj/src/main.rs"), 10);

    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let results = glob_search(&tree, tree.root, "**/node_modules", false).unwrap();

    assert_eq!(
        results.len(),
        1,
        "should match the node_modules dir itself, not descend into it"
    );
    assert!(results[0].relative_path.ends_with("node_modules"));

    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn glob_search_rejects_empty_pattern() {
    let root = tmp_root("glob-empty");
    write_file(&root.join("a.txt"), 10);
    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let err = glob_search(&tree, tree.root, "   ", false).unwrap_err();
    assert!(err.contains("empty"));
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn cleanup_candidates_need_their_project_markers() {
    let root = tmp_root("cleanup");
    write_file(&root.join("package.json"), 2);
    write_file(&root.join("Cargo.toml"), 2);
    write_file(&root.join("node_modules/pkg/index.js"), 10);
    write_file(&root.join("target/debug/bin"), 10);
    write_file(&root.join("src/main.rs"), 10);

    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let hits = cleanup_candidates(&tree, tree.root, &root);
    let names: Vec<&str> = hits
        .iter()
        .map(|h| tree.nodes[h.node as usize].name.as_ref())
        .collect();

    assert!(names.contains(&"node_modules"));
    assert!(names.contains(&"target"));
    assert!(!names.contains(&"src"));

    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn gitignored_children_are_flagged_from_the_nearest_gitignore() {
    let root = tmp_root("gitignore");
    fs::create_dir_all(root.join(".git")).unwrap();
    fs::write(root.join(".gitignore"), b"build/\n*.log\n").unwrap();
    write_file(&root.join("build/output.bin"), 10);
    write_file(&root.join("src/main.rs"), 10);
    write_file(&root.join("debug.log"), 10);

    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let hits = gitignored_children(&tree, tree.root, &root);
    let names: Vec<&str> = hits
        .iter()
        .map(|&id| tree.nodes[id as usize].name.as_ref())
        .collect();

    assert!(names.contains(&"build"));
    assert!(names.contains(&"debug.log"));
    assert!(!names.contains(&"src"));

    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn stay_on_filesystem_does_not_panic_on_normal_tree() {
    let root = tmp_root("stayfs");
    write_file(&root.join("a/b/c.txt"), 10);
    let mut opts = ScanOptions::new(&root);
    opts.stay_on_filesystem = true;
    let tree = scan(&opts).unwrap();
    assert!(tree.nodes.len() > 1);
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn precancelled_token_returns_cancelled_before_building_a_tree() {
    let root = tmp_root("cancel-pre");
    write_file(&root.join("a.txt"), 4096);
    write_file(&root.join("sub/b.txt"), 4096);

    let flag = CancelFlag::new();
    flag.cancel(); // already cancelled before the scan starts

    let result = scan_cancellable(&ScanOptions::new(&root), None, Some(&flag));
    assert!(
        matches!(result, Err(ScanError::Cancelled)),
        "a pre-cancelled flag must short-circuit the walk with Cancelled"
    );

    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn uncancelled_token_scans_normally() {
    let root = tmp_root("cancel-none");
    write_file(&root.join("a.txt"), 4096);
    write_file(&root.join("sub/b.txt"), 4096);

    let flag = CancelFlag::new(); // present but never tripped
    let tree = scan_cancellable(&ScanOptions::new(&root), None, Some(&flag))
        .expect("an uncancelled token must scan to completion");

    assert!(tree.nodes[tree.root as usize].size > 0);
    assert_eq!(
        tree.nodes[tree.root as usize].entry_count, 4,
        "root + a.txt + sub + sub/b.txt"
    );

    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn cancel_from_progress_stops_mid_traversal() {
    // Build a tree with plenty of entries so there is at least one iteration
    // after the first-entry progress tick fires and trips the flag.
    let root = tmp_root("cancel-mid");
    for i in 0..64 {
        write_file(&root.join(format!("dir{i:02}/file.txt")), 64);
    }

    let flag = CancelFlag::new();
    // The progress callback fires on the first processed entry (walk.rs), tripping
    // cancellation; the next loop iteration's checkpoint then returns Cancelled.
    let mut cancel_on_first_tick = |_processed: u64, _bytes: u64, _path: &str| {
        flag.cancel();
    };

    let result = scan_cancellable(
        &ScanOptions::new(&root),
        Some(&mut cancel_on_first_tick),
        Some(&flag),
    );
    assert!(
        matches!(result, Err(ScanError::Cancelled)),
        "cancelling from the first progress tick must stop traversal early"
    );

    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn scan_with_progress_reports_final_totals() {
    let root = tmp_root("progress");
    write_file(&root.join("a.txt"), 4096);
    write_file(&root.join("sub/b.txt"), 4096);

    let opts = ScanOptions::new(&root);
    let mut calls: Vec<(u64, u64, String)> = Vec::new();
    let mut cb = |processed: u64, total_bytes: u64, path: &str| {
        calls.push((processed, total_bytes, path.to_string()));
    };
    let tree = scan_with_progress(&opts, Some(&mut cb)).expect("scan should succeed");

    assert!(
        !calls.is_empty(),
        "expected at least the final progress call"
    );
    let (final_processed, final_bytes, final_path) = calls.last().unwrap();
    assert_eq!(final_path, "", "final call reports an empty-path sentinel");
    assert_eq!(*final_processed, 3, "a.txt + sub + sub/b.txt");
    assert_eq!(
        *final_bytes, tree.nodes[tree.root as usize].size,
        "running total matches the finished tree's root size"
    );

    fs::remove_dir_all(&root).unwrap();
}

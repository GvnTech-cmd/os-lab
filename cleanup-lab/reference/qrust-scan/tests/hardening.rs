//! CLN-22: one failing test per gap listed in `cleanup-lab/reference/README.md`.

use std::fs;
use std::path::{Path, PathBuf};

use qrust_scan::{
    cleanup_candidates, gitignored_children, glob_search, scan, Node, ScanOptions, Tree, NO_ID,
};

fn tmp_root(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("qrust-harden-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn touch(path: &Path) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, b"x").unwrap();
}

fn names(tree: &Tree, ids: &[u32]) -> Vec<String> {
    let mut v: Vec<String> = ids
        .iter()
        .map(|&i| tree.nodes[i as usize].name.to_string())
        .collect();
    v.sort();
    v
}

// --- nested .gitignore, .git/info/exclude, global excludes ------------------

#[test]
fn nested_gitignore_applies_below_its_own_directory_only() {
    let root = tmp_root("nested");
    fs::create_dir_all(root.join(".git")).unwrap();
    touch(&root.join("pkg/.gitignore"));
    fs::write(root.join("pkg/.gitignore"), b"generated/\n").unwrap();
    touch(&root.join("pkg/generated/a.txt"));
    touch(&root.join("pkg/keep/a.txt"));
    touch(&root.join("other/generated/a.txt"));

    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let pkg = tree
        .children(tree.root)
        .into_iter()
        .find(|&i| &*tree.nodes[i as usize].name == "pkg")
        .unwrap();
    let other = tree
        .children(tree.root)
        .into_iter()
        .find(|&i| &*tree.nodes[i as usize].name == "other")
        .unwrap();

    let in_pkg = gitignored_children(&tree, pkg, &root.join("pkg"));
    assert_eq!(names(&tree, &in_pkg), vec!["generated"]);
    let in_other = gitignored_children(&tree, other, &root.join("other"));
    assert!(
        in_other.is_empty(),
        "a nested .gitignore must not leak to siblings"
    );
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn deeper_gitignore_can_reinclude_what_a_parent_ignored() {
    let root = tmp_root("reinclude");
    fs::create_dir_all(root.join(".git")).unwrap();
    fs::write(root.join(".gitignore"), b"*.log\n").unwrap();
    fs::create_dir_all(root.join("logs")).unwrap();
    fs::write(root.join("logs/.gitignore"), b"!keep.log\n").unwrap();
    touch(&root.join("logs/keep.log"));
    touch(&root.join("logs/drop.log"));

    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let logs = tree
        .children(tree.root)
        .into_iter()
        .find(|&i| &*tree.nodes[i as usize].name == "logs")
        .unwrap();
    let hits = gitignored_children(&tree, logs, &root.join("logs"));
    assert_eq!(names(&tree, &hits), vec!["drop.log"]);
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn info_exclude_is_read() {
    let root = tmp_root("exclude");
    fs::create_dir_all(root.join(".git/info")).unwrap();
    fs::write(root.join(".git/info/exclude"), b"scratch/\n").unwrap();
    touch(&root.join("scratch/a.txt"));
    touch(&root.join("src/a.txt"));

    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let hits = gitignored_children(&tree, tree.root, &root);
    assert_eq!(names(&tree, &hits), vec!["scratch"]);
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn global_excludes_are_lowest_priority() {
    let root = tmp_root("global");
    fs::create_dir_all(root.join(".git")).unwrap();
    fs::write(root.join(".gitignore"), b"!.DS_Store\n").unwrap();
    touch(&root.join(".DS_Store"));
    touch(&root.join("notes.swp"));
    touch(&root.join("src/a.txt"));

    let global = root.join("global_ignore");
    fs::write(&global, b".DS_Store\n*.swp\n").unwrap();
    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let hits =
        qrust_scan::gitignore::gitignored_children_with(&tree, tree.root, &root, Some(&global));
    assert_eq!(
        names(&tree, &hits),
        vec!["notes.swp"],
        "repo .gitignore re-includes .DS_Store"
    );
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn entries_inside_an_ignored_directory_stay_ignored() {
    let root = tmp_root("parent-ignored");
    fs::create_dir_all(root.join(".git")).unwrap();
    fs::write(root.join(".gitignore"), b"build/\n").unwrap();
    fs::create_dir_all(root.join("build")).unwrap();
    fs::write(root.join("build/.gitignore"), b"!x.txt\n").unwrap();
    touch(&root.join("build/x.txt"));

    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let build = tree
        .children(tree.root)
        .into_iter()
        .find(|&i| &*tree.nodes[i as usize].name == "build")
        .unwrap();
    let hits = gitignored_children(&tree, build, &root.join("build"));
    assert_eq!(
        names(&tree, &hits),
        vec![".gitignore", "x.txt"],
        "git cannot re-include below an ignored directory"
    );
    fs::remove_dir_all(&root).unwrap();
}

// --- iterative glob ----------------------------------------------------------

fn chain_tree(depth: usize) -> Tree {
    let mut nodes = vec![node("root", NO_ID, true)];
    for i in 1..=depth {
        let parent = (i - 1) as u32;
        let id = i as u32;
        nodes.push(node(&format!("d{i}"), parent, true));
        nodes[parent as usize].first_child = id;
    }
    nodes.push(node("needle", depth as u32, false));
    let leaf = (depth + 1) as u32;
    nodes[depth].first_child = leaf;
    Tree {
        nodes,
        root: 0,
        io_errors: 0,
        elapsed: std::time::Duration::ZERO,
    }
}

fn node(name: &str, parent: u32, is_dir: bool) -> Node {
    Node {
        name: name.into(),
        parent,
        first_child: NO_ID,
        next_sibling: NO_ID,
        size: 0,
        entry_count: 1,
        mtime: 0,
        max_mtime: 0,
        is_dir,
        has_error: false,
    }
}

#[test]
fn glob_search_survives_a_very_deep_tree() {
    let tree = chain_tree(12_000);
    let hits = glob_search(&tree, tree.root, "**/needle", false).unwrap();
    assert_eq!(hits.len(), 1);
    assert!(hits[0].relative_path.ends_with("/needle"));
}

#[test]
fn glob_search_keeps_pre_order_and_pruning() {
    let root = tmp_root("glob-order");
    touch(&root.join("a/hit/inner/hit"));
    touch(&root.join("b/hit"));
    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let hits = glob_search(&tree, tree.root, "**/hit", false).unwrap();
    let mut paths: Vec<&str> = hits.iter().map(|h| h.relative_path.as_str()).collect();
    paths.sort();
    assert_eq!(paths, vec!["a/hit", "b/hit"], "no match below a match");
    fs::remove_dir_all(&root).unwrap();
}

// --- verified cleanup candidates ---------------------------------------------

#[test]
fn target_without_cargo_toml_is_not_a_candidate() {
    let root = tmp_root("target-plain");
    touch(&root.join("target/notes.txt"));
    touch(&root.join("src/main.rs"));
    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let hits = cleanup_candidates(&tree, tree.root, &root);
    assert!(hits.is_empty(), "a folder named target proves nothing");
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn markers_prove_each_signature() {
    let root = tmp_root("markers");
    touch(&root.join("rust/Cargo.toml"));
    touch(&root.join("rust/target/debug/bin"));
    touch(&root.join("maven/pom.xml"));
    touch(&root.join("maven/target/classes/A.class"));
    touch(&root.join("web/package.json"));
    touch(&root.join("web/node_modules/p/index.js"));
    touch(&root.join("py/.venv/pyvenv.cfg"));
    touch(&root.join("fake/.venv/readme.txt"));
    touch(&root.join("tagged/cache/CACHEDIR.TAG"));
    fs::write(
        root.join("tagged/cache/CACHEDIR.TAG"),
        b"Signature: 8a477f597d28d172789f06886806bc55\n# cache\n",
    )
    .unwrap();
    touch(&root.join("badtag/cache/CACHEDIR.TAG"));

    let tree = scan(&ScanOptions::new(&root)).unwrap();
    let find = |dir: &str| {
        let id = tree
            .children(tree.root)
            .into_iter()
            .find(|&i| &*tree.nodes[i as usize].name == dir)
            .unwrap();
        let hits = cleanup_candidates(&tree, id, &root.join(dir));
        hits.into_iter()
            .map(|h| (tree.nodes[h.node as usize].name.to_string(), h.signature_id))
            .collect::<Vec<_>>()
    };
    assert_eq!(find("rust"), vec![("target".to_string(), "rust_target")]);
    assert_eq!(find("maven"), vec![("target".to_string(), "maven_target")]);
    assert_eq!(
        find("web"),
        vec![("node_modules".to_string(), "node_modules")]
    );
    assert_eq!(find("py"), vec![(".venv".to_string(), "python_venv")]);
    assert!(
        find("fake").is_empty(),
        ".venv without pyvenv.cfg is not a virtualenv"
    );
    assert_eq!(find("tagged"), vec![("cache".to_string(), "cachedir_tag")]);
    assert!(
        find("badtag").is_empty(),
        "a CACHEDIR.TAG without the signature is ignored"
    );
    fs::remove_dir_all(&root).unwrap();
}

"""CLNP-23: the size-tree walker measures honestly over generated trees.

Every test walks a temp tree it just built; no real user folder is touched
(README rule 8).
"""
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import explorer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def make_tree(base):
    """base/big/{a,b}, a symlink, a hard link, an unreadable-free fixture."""
    big = os.path.join(base, "big")
    os.makedirs(os.path.join(big, "a"))
    os.makedirs(os.path.join(big, "b"))
    with open(os.path.join(big, "a", "one.bin"), "wb") as handle:
        handle.write(b"x" * 500)
    with open(os.path.join(big, "b", "two.bin"), "wb") as handle:
        handle.write(b"x" * 300)
    target = os.path.join(big, "a", "one.bin")
    link = os.path.join(big, "hard.bin")
    if hasattr(os, "link"):
        os.link(target, link)
    os.symlink(target, os.path.join(big, "alias.bin"))
    return big


class WalkTest(unittest.TestCase):
    def test_parent_summed_sizes_count_hard_links_once_and_skip_symlinks(self):
        with tempfile.TemporaryDirectory() as base:
            tree = make_tree(base)
            node, counters = explorer.walk(tree)
            self.assertFalse(counters["truncated"])
            # 500 + 300 counted once; the hard link (same inode) and the symlink add nothing
            self.assertEqual(node["sizeBytes"], 800)
            self.assertEqual(node["files"], 2)
            self.assertEqual(node["folders"], 2)
            names = [child["name"] for child in node["children"]]
            self.assertEqual(names, ["a", "b"])  # largest first
            self.assertEqual(node["children"][0]["sizeBytes"], 500)

    def test_budget_marks_the_tree_truncated_honestly(self):
        with tempfile.TemporaryDirectory() as base:
            tree = make_tree(base)
            node, counters = explorer.walk(tree, max_nodes=2)
            self.assertTrue(counters["truncated"])
            self.assertTrue(node["truncated"])

    def test_depth_budget_stops_descent(self):
        with tempfile.TemporaryDirectory() as base:
            tree = make_tree(base)
            node, _ = explorer.walk(tree, max_depth=1)
            self.assertTrue(node["children"][0]["truncated"])

    def test_cancel_stops_the_walk(self):
        with tempfile.TemporaryDirectory() as base:
            tree = make_tree(base)
            cancel = threading.Event()
            cancel.set()
            _node, counters = explorer.walk(tree, cancel=cancel)
            self.assertTrue(counters["cancelled"])


class RootsTest(unittest.TestCase):
    def test_registry_lists_deep_roots_and_refuses_unknown_ids(self):
        answer = explorer.roots(ROOT)
        ids = [item["id"] for item in answer]
        self.assertIn("home-projects", ids)
        with self.assertRaises(explorer.ExplorerError):
            explorer.resolve_root(ROOT, "not-a-root")
        with self.assertRaises(explorer.ExplorerError):
            explorer.resolve_root(ROOT, "/etc/passwd")

    def test_custom_overlay_entries_join_the_registry(self):
        from cleanup_lab import custom_catalog  # noqa: F401
        with tempfile.TemporaryDirectory() as base:
            env = {"HOME": base, "USERPROFILE": base, "OSLAB_CLEANUP_STATE": base, "PATH": ""}
            folder = os.path.join(base, "mydata")
            os.makedirs(folder)
            custom_catalog.add("My data", folder, [], platform=explorer.platform_id(), env=env)
            answer = explorer.roots(ROOT, env=env)
            custom = [item for item in answer if item["source"] == "custom"]
            self.assertEqual(len(custom), 1)
            self.assertEqual(custom[0]["id"], "custom.my-data")
            self.assertTrue(custom[0]["available"])


class ExploreTest(unittest.TestCase):
    def test_explore_resolves_a_registered_root(self):
        with tempfile.TemporaryDirectory() as base:
            os.makedirs(os.path.join(base, "projects", "demo"))
            with open(os.path.join(base, "projects", "demo", "f.bin"), "wb") as handle:
                handle.write(b"x" * 100)
            env = {"HOME": base, "USERPROFILE": base, "PATH": ""}
            root = tempfile.mkdtemp()
            os.makedirs(os.path.join(root, "cleanup-lab", "catalog"))
            with open(os.path.join(root, "cleanup-lab", "deep-roots.json"), "w") as handle:
                import json
                json.dump({"home-projects": "~/Projects"}, handle)
            payload = explorer.explore(root, "home-projects", env=env)
            self.assertEqual(payload["rootId"], "home-projects")
            self.assertEqual(payload["tree"]["sizeBytes"], 100)
            self.assertEqual(payload["nodes"], 2)  # the root plus the demo folder

    def test_drilldown_stays_inside_the_root(self):
        with tempfile.TemporaryDirectory() as base:
            root = tempfile.mkdtemp()
            os.makedirs(os.path.join(root, "cleanup-lab", "catalog"))
            with open(os.path.join(root, "cleanup-lab", "deep-roots.json"), "w") as handle:
                import json
                json.dump({"home-projects": base}, handle)
            inside = os.path.join(base, "sub")
            os.makedirs(inside)
            with open(os.path.join(inside, "f.bin"), "wb") as handle:
                handle.write(b"x" * 50)
            payload = explorer.explore(root, "home-projects", env={"HOME": base, "USERPROFILE": base, "PATH": ""},
                                      relative="sub")
            self.assertEqual(payload["tree"]["sizeBytes"], 50)
            for bad in ("../outside", "/etc", "sub/../../.."):
                with self.assertRaises(explorer.ExplorerError):
                    explorer.explore(root, "home-projects", env={"HOME": base, "USERPROFILE": base, "PATH": ""},
                                     relative=bad)


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import time
import unittest

from cleanup_ref import artifacts as art


def touch(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def test_name_alone_is_not_enough(self):
        os.makedirs(self.p("photos", "target"))
        os.makedirs(self.p("notes", "node_modules"))
        os.makedirs(self.p("venv"))
        self.assertIsNone(art.classify_dir(self.p("photos", "target")))
        self.assertIsNone(art.classify_dir(self.p("notes", "node_modules")))
        self.assertIsNone(art.classify_dir(self.p("venv")))

    def test_markers_prove_the_artifact(self):
        touch(self.p("rs", "Cargo.toml"))
        os.makedirs(self.p("rs", "target"))
        touch(self.p("java", "pom.xml"))
        os.makedirs(self.p("java", "target"))
        touch(self.p("py", ".venv", "pyvenv.cfg"))
        self.assertEqual(art.classify_dir(self.p("rs", "target")).id, "rust_target")
        self.assertEqual(art.classify_dir(self.p("java", "target")).id, "maven_target")
        self.assertEqual(art.classify_dir(self.p("py", ".venv")).id, "python_venv")

    def test_cachedir_tag_must_carry_the_signature(self):
        touch(self.p("good", "CACHEDIR.TAG"), art.CACHEDIR_SIGNATURE + b"\n# tool\n")
        touch(self.p("bad", "CACHEDIR.TAG"), b"Signature: nope")
        self.assertEqual(art.classify_dir(self.p("good")).id, "cachedir_tag")
        self.assertIsNone(art.classify_dir(self.p("bad")))

    def test_symlinked_directory_is_never_classified_or_followed(self):
        touch(self.p("real", "package.json"))
        os.makedirs(self.p("real", "node_modules"))
        os.makedirs(self.p("scan"))
        os.symlink(self.p("real"), self.p("scan", "linked-project"))
        self.assertEqual(list(art.sweep([self.p("scan")])), [])

    def test_sweep_stops_at_match_skips_vcs_and_respects_idle_filter(self):
        touch(self.p("app", "package.json"))
        touch(self.p("app", "node_modules", "dep", "package.json"))
        os.makedirs(self.p("app", "node_modules", "dep", "node_modules"))
        touch(self.p(".git", "objects", "x"))
        touch(self.p("lib", "Cargo.toml"))
        os.makedirs(self.p("lib", "target"))
        os.makedirs(self.p("lib", "src", "__pycache__"))

        stats = art.SweepStats()
        found = sorted((os.path.relpath(f.path, self.root), f.signature_id) for f in art.sweep([self.root], stats=stats))
        self.assertEqual(found, [
            (os.path.join("app", "node_modules"), "node_modules"),
            (os.path.join("lib", "src", "__pycache__"), "python_pycache"),
            (os.path.join("lib", "target"), "rust_target"),
        ])

        old = time.time() - 100 * 86_400
        os.utime(self.p("lib", "Cargo.toml"), (old, old))
        idle = {f.signature_id for f in art.sweep([self.root], min_idle_days=30)}
        self.assertIn("rust_target", idle)
        self.assertNotIn("node_modules", idle, "package.json was just written: project is active")

    def test_cancel_stops_the_sweep(self):
        touch(self.p("a", "package.json"))
        os.makedirs(self.p("a", "node_modules"))
        stats = art.SweepStats()
        self.assertEqual(list(art.sweep([self.root], should_cancel=lambda: True, stats=stats)), [])
        self.assertTrue(stats.cancelled)

    def test_unreadable_directory_is_counted_not_fatal(self):
        if os.name == "nt" or os.geteuid() == 0:
            self.skipTest("permission bits are not enforced here")
        os.makedirs(self.p("locked"))
        os.chmod(self.p("locked"), 0)
        try:
            stats = art.SweepStats()
            list(art.sweep([self.root], stats=stats))
            self.assertEqual(stats.unreadable, 1)
        finally:
            os.chmod(self.p("locked"), 0o700)


if __name__ == "__main__":
    unittest.main()

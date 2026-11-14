"""CLN-24 marker fixtures."""
import os
import pathlib
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import artifacts, deep  # noqa: E402
ROOT = str(pathlib.Path(__file__).resolve().parents[3])

class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        self.projects = self.home / 'Projects'
        self.projects.mkdir()
        self.signatures = artifacts.load(ROOT)

    def tearDown(self):
        self.temp.cleanup()

    def test_target_requires_real_project_marker(self):
        project = self.projects / 'arbitrary'
        project.mkdir()
        target = project / 'target'
        target.mkdir()
        self.assertIsNone(artifacts.classify_dir(str(target), self.signatures))
        (project / 'Cargo.toml').write_text('[package]')
        self.assertEqual(artifacts.classify_dir(str(target), self.signatures).id, 'projects.rust-target')
        (project / 'Cargo.toml').unlink()
        (project / 'Cargo.toml').symlink_to('/etc/hosts')
        self.assertIsNone(artifacts.classify_dir(str(target), self.signatures))

    def test_venv_and_valid_cachedir_tag(self):
        project = self.projects / 'python'
        project.mkdir()
        venv = project / '.venv'
        venv.mkdir()
        self.assertIsNone(artifacts.classify_dir(str(venv), self.signatures))
        (venv / 'pyvenv.cfg').write_text('home=/usr/bin')
        self.assertEqual(artifacts.classify_dir(str(venv), self.signatures).id, 'projects.python-venv')
        cache = project / 'ordinary'
        cache.mkdir()
        (cache / 'CACHEDIR.TAG').write_bytes(b'wrong')
        self.assertIsNone(artifacts.classify_dir(str(cache), self.signatures))
        (cache / 'CACHEDIR.TAG').write_bytes(artifacts.CACHEDIR_SIGNATURE + b'\n')
        self.assertEqual(artifacts.classify_dir(str(cache), self.signatures).id, 'projects.cachedir-tag')

    def test_sweep_reports_ecosystem_regeneration_and_marker_age(self):
        project = self.projects / 'web'
        project.mkdir()
        marker = project / 'package.json'
        marker.write_text('{}')
        cache = project / 'node_modules'
        cache.mkdir()
        (cache / 'one').write_bytes(b'123')
        old = 1_600_000_000
        os.utime(marker, (old, old))
        args = dict(env={'HOME': str(self.home)}, platform='linux', clock=lambda: old + 40*86400)
        item = deep.sweep(ROOT, ['home-projects'], min_idle_days=30, **args)['items'][0]
        self.assertEqual((item['id'], item['ecosystem'], item['idleDays'], item['sizeBytes']),
                         ('projects.node-modules', 'Node.js', 40, 3))
        self.assertIn('install', item['regenerate'])
        self.assertEqual(deep.sweep(ROOT, ['home-projects'], min_idle_days=50, **args)['items'], [])

if __name__ == '__main__':
    unittest.main()

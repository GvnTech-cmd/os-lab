"""CLN-07 generated tree and simulator inventory tests."""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import deep  # noqa: E402
ROOT = str(pathlib.Path(__file__).resolve().parents[3])

class DeepTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        self.projects = self.home / 'Projects'
        self.projects.mkdir()
        self.env = {'HOME': str(self.home)}

    def tearDown(self):
        self.temp.cleanup()

    def test_generated_tree_and_stop_at_match(self):
        web = self.projects / 'web'
        web.mkdir()
        (web / 'package.json').write_text('{}')
        cache = web / 'node_modules'
        cache.mkdir()
        (cache / 'file').write_bytes(b'12345')
        nested = cache / 'nested'
        nested.mkdir()
        (nested / 'package.json').write_text('{}')
        (nested / 'node_modules').mkdir()
        rust = self.projects / 'rust'
        rust.mkdir()
        (rust / 'Cargo.toml').write_text('[package]')
        (rust / 'target').mkdir()
        (rust / 'target' / 'build').write_bytes(b'abc')
        other = self.projects / 'other'
        other.mkdir()
        (other / 'target').mkdir()
        (other / 'node_modules').mkdir()
        (self.projects / 'loop').symlink_to(self.projects)
        result = deep.sweep(ROOT, ['home-projects'], env=self.env, platform='linux')
        self.assertEqual({x['id'] for x in result['items']}, {'projects.node-modules', 'projects.rust-target'})
        self.assertEqual(sorted(x['sizeBytes'] for x in result['items']), [3, 7])

    def test_root_and_idle_validation(self):
        with self.assertRaises(deep.DeepError):
            deep.sweep(ROOT, ['/tmp'], env=self.env, platform='linux')
        with self.assertRaises(deep.DeepError):
            deep.sweep(ROOT, ['home-projects'], min_idle_days=True, env=self.env, platform='linux')
        self.assertTrue(next(x for x in deep.roots(ROOT, env=self.env, platform='linux')
                             if x['id'] == 'home-projects')['available'])

    def test_simulator_inventory_and_size(self):
        udid = 'A1B2C3D4-1111-2222-3333-444455556666'
        device = self.home / 'Library/Developer/CoreSimulator/Devices' / udid
        device.mkdir(parents=True)
        (device / 'data').write_bytes(b'1234')
        payload = {'devices': {'runtime': [{'udid': udid, 'name': 'iPhone', 'state': 'Shutdown',
                                           'isAvailable': False}]}}
        def fake_run(argv, **kwargs):
            self.assertEqual(argv, ['xcrun', 'simctl', 'list', '-j', 'devices'])
            self.assertFalse(kwargs['shell'])
            self.assertEqual(kwargs['timeout'], 5)
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr='')
        result = deep.simulators(ROOT, platform='macos', env=self.env, run=fake_run)
        self.assertEqual(result['devices'][0]['sizeBytes'], 4)
        self.assertFalse(result['devices'][0]['available'])
        self.assertFalse(deep.simulators(ROOT, platform='linux')['available'])

if __name__ == '__main__':
    unittest.main()

"""CLN-09 macOS leftover identity fixtures, including close nonmatches."""
import json
import os
import pathlib
import plistlib
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import leftovers_macos  # noqa: E402

class LeftoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.repo = self.base / 'repo'
        catalog = self.repo / 'cleanup-lab/catalog/signatures'
        catalog.mkdir(parents=True)
        config = {
            'version': 1, 'family': 'leftovers.macos',
            'appRoots': ['~/Applications'],
            'candidateRoots': [
                {'kind':'container','path':'~/Library/Containers','match':'bundle'},
                {'kind':'group-container','path':'~/Library/Group Containers','match':'team'},
                {'kind':'preference','path':'~/Library/Preferences','match':'bundle','suffix':'.plist'},
                {'kind':'app-support','path':'~/Library/Application Support','match':'name'},
            ],
            'largeAppDataBytes': 4,
        }
        (catalog / 'macos-leftovers.json').write_text(json.dumps(config))
        apps = self.home / 'Applications'
        apps.mkdir()
        app = apps / 'Acme Editor.app' / 'Contents'
        app.mkdir(parents=True)
        with (app / 'Info.plist').open('wb') as handle:
            plistlib.dump({'CFBundleIdentifier':'com.acme.editor', 'CFBundleName':'Acme Editor',
                           'TeamIdentifier':'TEAMID1234'}, handle)
        for name in ('Containers', 'Group Containers', 'Preferences', 'Application Support'):
            (self.home / 'Library' / name).mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_component_identity_and_near_misses(self):
        lib = self.home / 'Library'
        (lib / 'Containers' / 'com.acme.editor').mkdir()
        (lib / 'Containers' / 'com.acme.editor2').mkdir()
        (lib / 'Group Containers' / 'TEAMID1234.group.com.acme').mkdir()
        (lib / 'Group Containers' / 'TEAMID1235.group.com.acme').mkdir()
        (lib / 'Preferences' / 'com.acme.editor.plist').write_bytes(b'plist')
        (lib / 'Preferences' / 'com.acme.editor2.plist').write_bytes(b'plist')
        (lib / 'Application Support' / 'Acme Editor').mkdir()
        (lib / 'Application Support' / 'Acme Editor Pro').mkdir()
        result = leftovers_macos.scan(str(self.repo), env={'HOME':str(self.home)}, platform='macos')
        items = {x['name']:x for x in result['items']}
        self.assertEqual(result['installedCount'], 1)
        for name in ('com.acme.editor', 'TEAMID1234.group.com.acme', 'com.acme.editor.plist', 'Acme Editor'):
            self.assertEqual(items[name]['status'], 'installed', name)
        for name in ('com.acme.editor2', 'TEAMID1235.group.com.acme', 'com.acme.editor2.plist', 'Acme Editor Pro'):
            self.assertEqual(items[name]['status'], 'orphan', name)
        self.assertEqual(items['com.acme.editor2']['rule'], 'bundle-id')
        self.assertTrue(all(x['reportOnly'] for x in result['items']))

    def test_hidden_app_large_data_and_symlink_skip(self):
        apps = self.home / 'Applications'
        hidden = apps / '.Hidden.app' / 'Contents'
        hidden.mkdir(parents=True)
        with (hidden / 'Info.plist').open('wb') as handle:
            plistlib.dump({'CFBundleIdentifier':'com.example.hidden'}, handle)
        support = self.home / 'Library/Application Support'
        large = support / 'BigData'
        large.mkdir()
        (large / 'blob').write_bytes(b'x' * 5)
        (support / 'Link').symlink_to(large)
        result = leftovers_macos.scan(str(self.repo), env={'HOME':str(self.home)}, platform='macos')
        self.assertIn('leftovers.macos.hidden-app', {x['id'] for x in result['items']})
        self.assertIn('leftovers.macos.large-app-data', {x['id'] for x in result['items']})
        self.assertNotIn('Link', {x['name'] for x in result['items']})

    def test_non_macos_is_unavailable(self):
        self.assertFalse(leftovers_macos.scan(str(self.repo), platform='linux')['available'])

    def test_empty_app_inventory_does_not_claim_orphans(self):
        shutil.rmtree(self.home / 'Applications')
        container = self.home / 'Library/Containers/com.acme.editor'
        container.mkdir()
        result = leftovers_macos.scan(str(self.repo), env={'HOME':str(self.home)}, platform='macos')
        self.assertEqual(result['items'][0]['status'], 'unknown')
        self.assertEqual(result['items'][0]['confidence'], 0.0)

if __name__ == '__main__':
    unittest.main()

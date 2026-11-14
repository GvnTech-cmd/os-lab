"""CLN-10 Linux/Windows inventory and close-name fixtures."""
import os
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import leftovers_cross  # noqa: E402
ROOT = str(pathlib.Path(__file__).resolve().parents[3])

class CrossLeftoversTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        for relative in ('.config', '.local/share', '.cache'):
            (self.home / relative).mkdir(parents=True)
        self.env = {'HOME': str(self.home), 'PATH': '/fake'}

    def tearDown(self):
        self.temp.cleanup()

    def test_linux_inventory_and_near_miss(self):
        (self.home / '.config/firefox').mkdir()
        (self.home / '.config/firefox-old').mkdir()
        (self.home / '.cache/org.mozilla.Firefox').mkdir()
        calls = []
        def which(name, path):
            return '/fake/' + name if name in ('dpkg-query', 'flatpak') else None
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            output = 'firefox\n' if argv[0].endswith('dpkg-query') else 'org.mozilla.Firefox\n'
            return SimpleNamespace(returncode=0, stdout=output)
        report = leftovers_cross.scan(ROOT, platform='linux', env=self.env, which=which, runner=runner)
        items = {x['name']:x for x in report['items']}
        self.assertEqual(items['firefox']['status'], 'installed')
        self.assertEqual(items['firefox-old']['status'], 'orphan')
        self.assertEqual(items['org.mozilla.Firefox']['status'], 'installed')
        self.assertEqual(report['inventorySources'], ['dpkg', 'flatpak'])
        self.assertTrue(all(not opts['shell'] and opts['timeout'] == 10 for _, opts in calls))

    def test_failed_inventory_makes_nonmatch_unknown(self):
        (self.home / '.config/other').mkdir()
        def runner(argv, **kwargs):
            return SimpleNamespace(returncode=1, stdout='')
        report = leftovers_cross.scan(ROOT, platform='linux', env=self.env,
                                      which=lambda name,path: '/fake/' + name if name == 'dpkg-query' else None,
                                      runner=runner)
        self.assertEqual(report['items'][0]['status'], 'unknown')
        self.assertEqual(report['items'][0]['rule'], 'installed-inventory-empty')
        self.assertTrue(report['inventoryErrors'])

    def test_windows_registry_exact_name(self):
        appdata = self.home / 'AppData'
        appdata.mkdir()
        (appdata / 'Acme Editor').mkdir()
        (appdata / 'Acme Editor Pro').mkdir()
        report = leftovers_cross.scan(ROOT, platform='windows', env=self.env,
                    registry_reader=lambda: [{'displayName':'Acme Editor', 'key':'{guid}'}],
                    root_override=[('appdata', str(appdata))])
        items = {x['name']:x for x in report['items']}
        self.assertEqual(items['Acme Editor']['status'], 'installed')
        self.assertEqual(items['Acme Editor Pro']['status'], 'orphan')
        self.assertTrue(all(x['reportOnly'] for x in report['items']))
        self.assertEqual(report['inventorySources'], ['uninstall-registry'])

if __name__ == '__main__':
    unittest.main()

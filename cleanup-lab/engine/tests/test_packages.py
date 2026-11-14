"""CLN-11 parsers on captured-style inventory output."""
import os
import pathlib
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import packages  # noqa: E402

class PackageTests(unittest.TestCase):
    def test_typed_preview_parses_all_three_managers_without_uninstall(self):
        outputs = {
            'brew': 'Would uninstall:\n  orphan-formula\n  other@2\n',
            'pip3': '[{"name":"httpx","version":"1.2"},{"name":"--force","version":"0"}]',
            'gem': '*** LOCAL GEMS ***\n\nrake\n--force\n',
        }
        calls = []
        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return SimpleNamespace(returncode=0, stdout=outputs[pathlib.Path(argv[0]).name], stderr='')
        result = packages.inventory(platform='macos', env={'PATH':'/fake'},
                    which=lambda name,path: '/fake/' + name, runner=run)
        names = {item['name']:item for item in result['items']}
        self.assertEqual(set(names), {'orphan-formula','other@2','httpx','rake'})
        self.assertEqual(names['orphan-formula']['uninstallArgv'],
                         ['/fake/brew','uninstall','--formula','orphan-formula'])
        self.assertEqual(names['httpx']['uninstallArgv'], ['/fake/pip3','uninstall','httpx'])
        self.assertEqual(names['rake']['uninstallArgv'], ['/fake/gem','uninstall','rake'])
        self.assertTrue(all(item['reportOnly'] for item in result['items']))
        self.assertTrue(all('uninstall' not in argv and opts['shell'] is False
                            and opts['timeout'] == 15 for argv,opts in calls))

    def test_failed_parser_reports_error_without_false_candidates(self):
        def run(argv, **kwargs):
            return SimpleNamespace(returncode=0, stdout='not json', stderr='')
        result = packages.inventory(platform='windows', env={'PATH':'/fake'},
                    which=lambda name,path: '/fake/' + name if name == 'pip3' else None,
                    runner=run)
        self.assertFalse(result['available'])
        self.assertEqual(result['items'], [])
        self.assertEqual(result['errors'][0]['tool'], 'pip3')

    def test_missing_managers_hide_inventory(self):
        result = packages.inventory(platform='linux', env={'PATH':''}, which=lambda name,path: None)
        self.assertFalse(result['available'])
        self.assertEqual(result['items'], [])

if __name__ == '__main__':
    unittest.main()

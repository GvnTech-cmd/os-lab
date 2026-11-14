"""CLN-08 typed container actions against a fake Docker/Podman binary."""
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import containers, vms  # noqa: E402
ROOT = str(pathlib.Path(__file__).resolve().parents[3])

class ContainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        script = self.base / 'docker'
        script.write_text('#!' + sys.executable + '\n'
                          'import json,os,sys\n'
                          'a=sys.argv[1:]\n'
                          'if a==["info"]: print("ready"); sys.exit(0)\n'
                          'if a[:2]==["image","ls"]: print(json.dumps({"ID":os.getenv("FAKE_ID","one")})); sys.exit(0)\n'
                          'if a[:2]==["image","prune"]:\n'
                          ' open(os.environ["FAKE_LOG"],"a").write("pruned\\n"); print("Total reclaimed space: 3B"); sys.exit(0)\n'
                          'sys.exit(2)\n')
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        self.env = {'PATH': str(self.base), 'FAKE_LOG': str(self.base / 'log')}

    def tearDown(self):
        self.temp.cleanup()

    def test_fake_docker_preview_then_typed_prune(self):
        caps = containers.capabilities(ROOT, env=self.env)
        self.assertTrue(caps['available'])
        self.assertEqual(caps['engine'], 'docker')
        self.assertTrue(all(not x['defaultSelected'] for x in caps['actions']))
        self.assertEqual(next(x for x in caps['actions'] if x['risk'] == 'high')['id'],
                         'containers.docker.dangling-volumes')
        plan, rows = containers.preview(ROOT, 'containers.docker.dangling-images', env=self.env)
        self.assertEqual(rows, [{'ID': 'one'}])
        self.assertEqual(plan.prune_argv, ('image', 'prune', '--force'))
        result = containers.execute(ROOT, plan, env=self.env)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual((self.base / 'log').read_text(), 'pruned\n')

    def test_stale_preview_never_prunes(self):
        plan, _ = containers.preview(ROOT, 'containers.docker.dangling-images', env=self.env)
        with self.assertRaisesRegex(containers.ContainerError, 'changed'):
            containers.execute(ROOT, plan, env=dict(self.env, FAKE_ID='two'))
        self.assertFalse((self.base / 'log').exists())

    def test_no_engine_hides_actions(self):
        self.assertFalse(containers.capabilities(ROOT, env={'PATH': str(self.base / 'absent')})['available'])
        with self.assertRaises(containers.ContainerError):
            containers.preview(ROOT, 'containers.docker.dangling-images', env={'PATH': ''})

    def test_podman_fallback_when_docker_does_not_answer(self):
        (self.base / 'docker').write_text('#!' + sys.executable + '\nimport sys\nsys.exit(1)\n')
        (self.base / 'docker').chmod(0o700)
        podman = self.base / 'podman'
        podman.write_text('#!' + sys.executable + '\nimport sys\n'
                          'if sys.argv[1:]==["info"]: print("ready"); sys.exit(0)\n'
                          'sys.exit(2)\n')
        podman.chmod(0o700)
        caps = containers.capabilities(ROOT, env=self.env)
        self.assertEqual(caps['engine'], 'podman')
        self.assertNotIn('containers.podman.build-cache', {x['id'] for x in caps['actions']})

    def test_vm_report_only(self):
        home = self.base / 'home'
        bundle = home / 'VirtualBox VMs' / 'demo'
        bundle.mkdir(parents=True)
        (bundle / 'demo.vbox').write_bytes(b'config')
        (bundle / 'disk.vdi').write_bytes(b'diskbytes')
        report = vms.inventory(ROOT, platform='linux', env={'HOME': str(home)})
        self.assertEqual(len(report['items']), 1)
        self.assertEqual(report['items'][0]['id'], 'vms.virtualbox')
        self.assertEqual(report['items'][0]['sizeBytes'], 15)
        self.assertTrue(report['items'][0]['reportOnly'])

if __name__ == '__main__':
    unittest.main()

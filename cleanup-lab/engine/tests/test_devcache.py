"""CLN-25 dynamic cache sources with fake paths and fixed probe results."""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import catalog, clean, devcache, scan  # noqa: E402

ROOT = str(pathlib.Path(__file__).resolve().parents[3])


class DeveloperCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cln-devcache-")
        self.base = pathlib.Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {"HOME": str(self.home), "PATH": ""}
        self.entries = {entry["id"]: entry for entry in catalog.load(ROOT, self.env)}

    def tearDown(self):
        self.temp.cleanup()

    def test_environment_precedes_probe_and_default(self):
        chosen = self.base / "npm-custom"
        entry = self.entries["developers.npm"]
        result = devcache.resolve(entry, "linux", dict(self.env, npm_config_cache=str(chosen)),
                                  str(self.home), str(self.home / ".npm"),
                                  probe=lambda *_: self.fail("probe must not run"))
        self.assertEqual((result.path, result.source), (str(chosen), "env:npm_config_cache"))
        report = catalog.report(ROOT, platform="linux", env=dict(self.env, npm_config_cache=str(chosen)))
        npm = next(item for item in report["entries"] if item["id"] == "developers.npm")
        self.assertEqual(npm["paths"][0]["source"], "env:npm_config_cache")

    def test_valid_probe_precedes_default_and_bad_probe_falls_back(self):
        entry = self.entries["developers.pip"]
        default = str(self.home / ".cache" / "pip")
        good = devcache.resolve(entry, "linux", self.env, str(self.home), default,
                                probe=lambda *_: "/opt/pip-cache")
        self.assertEqual((good.path, good.source), ("/opt/pip-cache", "probe:pip3 cache dir"))
        for bad in ("undefined", "Usage Error: no", "relative/path", "/", str(self.home), "one\ntwo", None):
            result = devcache.resolve(entry, "linux", self.env, str(self.home), default,
                                      probe=lambda *_, value=bad: value)
            self.assertEqual((result.path, result.source), (default, "default"), bad)

    def test_suffix_and_scan_source(self):
        cargo_home = self.base / "cargo-home"
        registry = cargo_home / "registry"
        registry.mkdir(parents=True)
        (registry / "cache.bin").write_bytes(b"x" * 16)
        env = dict(self.env, CARGO_HOME=str(cargo_home))
        entry = self.entries["developers.cargo-registry"]
        result = scan.scan_catalog(ROOT, [entry["id"]], env=env, platform="linux",
                                   catalog_entries=[entry])
        path = result["entries"][0]["paths"][0]
        self.assertEqual((path["path"], path["source"]), (str(registry), "env:CARGO_HOME"))
        self.assertEqual(result["totals"]["sizeBytes"], 16)
        plan = clean.build_plan(ROOT, [entry["id"]], env=env, platform="linux",
                                catalog_entries=[entry], names=())
        self.assertEqual(plan.payload["items"][0]["source"], "env:CARGO_HOME")
        self.assertEqual(clean._result_item(plan.payload["items"][0], "skipped")["source"],
                         "env:CARGO_HOME")

    def test_fixed_probe_runner_has_timeout_and_no_shell(self):
        calls = []
        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return SimpleNamespace(returncode=0, stdout="/opt/cache\n")
        answer = devcache.run_probe(["npm", "config", "get", "cache"], self.env,
                                    which=lambda name, path: "/fake/npm", run=fake_run)
        self.assertEqual(answer, "/opt/cache")
        self.assertEqual(calls[0][0], ["/fake/npm", "config", "get", "cache"])
        self.assertFalse(calls[0][1]["shell"])
        self.assertEqual(calls[0][1]["timeout"], 5)

    def test_probe_allowlist_and_toolchains(self):
        for key in ("npm", "pnpm", "yarn", "pip", "homebrew", "go-build", "go-mod"):
            entry = self.entries["developers." + key]
            self.assertEqual(tuple(entry["probeArgv"]), devcache.PROBE_ALLOWLIST[entry["id"]])
        for key in ("rustup", "nvm", "pyenv"):
            self.assertFalse(self.entries["developers." + key]["cleanable"])
        with open(pathlib.Path(ROOT) / "cleanup-lab/catalog/developers.json", encoding="utf-8") as handle:
            raw = next(item for item in json.load(handle)["entries"]
                       if item["id"] == "developers.npm")
        bad = dict(raw, probeArgv=["sh", "-c", "echo /tmp"])
        with self.assertRaises(catalog.CatalogError):
            catalog._check_entry(bad, "developers", "fixture.json", 0)
        for invalid in ([], ["X", "X"], ["BAD-NAME"]):
            with self.subTest(invalid=invalid), self.assertRaises(catalog.CatalogError):
                catalog._check_entry(dict(raw, cacheEnv=invalid), "developers", "fixture.json", 0)


if __name__ == "__main__":
    unittest.main()

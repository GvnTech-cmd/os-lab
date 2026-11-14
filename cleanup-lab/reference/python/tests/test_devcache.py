import os
import unittest

from cleanup_ref import devcache as dc

HOME = os.path.normpath("/home/student") if os.name != "nt" else "C:\\Users\\student"


def no_tools(_name):
    return None


def all_tools(name):
    return f"/usr/bin/{name}"


class DevCacheTests(unittest.TestCase):
    def test_env_wins_over_probe_and_default(self):
        calls = []
        res = dc.resolve(dc.KINDS_BY_ID["npm"], env={"npm_config_cache": HOME + "/custom-npm"}, os_name="linux",
                         home=HOME, probe=lambda argv: calls.append(argv) or "/elsewhere", which=all_tools)
        self.assertEqual(res.path, os.path.normpath(HOME + "/custom-npm"))
        self.assertEqual(res.source, "env:npm_config_cache")
        self.assertEqual(calls, [], "no probe when the environment already answers")

    def test_env_suffix_is_applied(self):
        res = dc.resolve(dc.KINDS_BY_ID["cargo_registry"], env={"CARGO_HOME": "/opt/cargo"}, os_name="linux",
                         home=HOME, which=no_tools)
        self.assertEqual(res.path, os.path.normpath("/opt/cargo/registry"))

    def test_probe_answer_is_used_only_when_valid(self):
        kind = dc.KINDS_BY_ID["go_build"]
        good = dc.resolve(kind, env={}, os_name="linux", home=HOME, probe=lambda a: "/srv/gocache", which=all_tools)
        self.assertEqual((good.path, good.source), (os.path.normpath("/srv/gocache"), "probe:go env GOCACHE"))
        for junk in ("undefined", "Usage Error: nope", "relative/dir", "", None):
            res = dc.resolve(kind, env={}, os_name="linux", home=HOME, probe=lambda a, j=junk: j, which=all_tools)
            self.assertEqual(res.source, "default", junk)

    def test_probe_is_skipped_when_binary_missing(self):
        res = dc.resolve(dc.KINDS_BY_ID["pip"], env={}, os_name="linux", home=HOME,
                         probe=lambda a: self.fail("must not probe"), which=no_tools)
        self.assertEqual(res.path, os.path.normpath(HOME + "/.cache/pip"))

    def test_defaults_follow_the_os(self):
        kind = dc.KINDS_BY_ID["pip"]
        mac = dc.resolve(kind, env={}, os_name="darwin", home=HOME, which=no_tools)
        linux = dc.resolve(kind, env={"XDG_CACHE_HOME": "/xdg"}, os_name="linux", home=HOME, which=no_tools)
        win = dc.resolve(kind, env={"LOCALAPPDATA": "/win/Local"}, os_name="win32", home=HOME, which=no_tools)
        self.assertEqual(mac.path, os.path.normpath(HOME + "/Library/Caches/pip"))
        self.assertEqual(linux.path, os.path.normpath("/xdg/pip"))
        self.assertEqual(win.path, os.path.normpath("/win/Local/pip/Cache"))
        cocoapods_linux = dc.resolve(dc.KINDS_BY_ID["cocoapods"], env={}, os_name="linux", home=HOME, which=no_tools)
        self.assertEqual((cocoapods_linux.path, cocoapods_linux.source), (None, "unsupported"))

    def test_toolchains_are_not_cache(self):
        classes = {k.id: k.risk_class for k in dc.KINDS}
        self.assertEqual(classes["rustup"], "toolchain")
        self.assertEqual(classes["cargo_home"], "toolchain")
        self.assertEqual(classes["npm"], "cache")

    def test_probe_runner_never_uses_a_shell_and_survives_missing_binary(self):
        self.assertIsNone(dc.run_probe(["definitely-not-a-real-binary-oslab", "x"]))


if __name__ == "__main__":
    unittest.main()

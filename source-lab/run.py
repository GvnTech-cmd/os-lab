#!/usr/bin/env python3
"""Local Source Lab entry point. Uses Python's standard library only."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

LAB_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_ROOT / "engine"))


def status() -> dict:
    from source_lab.paths import Paths

    paths = Paths.from_env()
    ancestor = paths.storage
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    writable = ancestor.is_dir() and os.access(ancestor, os.W_OK | os.X_OK)
    return {
        "lab": "source",
        "state": "ready" if writable and sys.version_info >= (3, 11) else "needs-setup",
        "python": {"version": sys.version.split()[0], "required": ">=3.11"},
        "storage": {"path": str(paths.storage), "exists": paths.storage.is_dir(), "writable": writable},
        "resources": {"path": str(paths.resources), "exists": paths.resources.is_dir(), "required": False},
        "optional": {"git": bool(shutil.which("git")), "node": bool(shutil.which("node")),
                     "tree_sitter": importlib.util.find_spec("tree_sitter") is not None,
                     "playwright": importlib.util.find_spec("playwright") is not None},
        "capabilities": ["static-detection", "structural-map", "crawler", "merge", "csv-merge"],
        "actions": ["doctor", "setup", "status", "contracts", "detect", "map", "crawl", "merge", "merge-csvs", "import-legacy"],
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args.pop(0) if args else "help"
    if command in ("help", "-h", "--help"):
        print("Source Lab — local, authorized source and package analysis\n\n"
              "Usage: labctl source <command> [options]\n"
              "  status, doctor [--json]  Read-only readiness and optional-tool checks\n"
              "  setup                   Create private local storage (no downloads)\n"
              "  detect TARGET [options] Analyze a local target; --help lists formats/runtime options\n"
              "  contracts [options]     Export/validate engine contracts and generated types\n"
              "  map [options]           Generate/query a structural source map\n"
              "  crawl [options]         Analyze explicitly selected repositories (may contact GitHub)\n"
              "  merge [options]         Preview/build a merged extension (may acquire selected sources)\n"
              "  merge-csvs [options]    Join operator-provided catalogs\n"
              "  import-legacy [options] Dry-run/copy authorized analysis artifacts\n\n"
              "SOURCE_LAB_STORAGE and SOURCE_LAB_RESOURCES override local data roots.\n"
              "No third-party archives, datasets or binaries are bundled.")
        return 0
    if sys.version_info < (3, 11):
        print("Source Lab requires Python 3.11 or newer.", file=sys.stderr)
        return 1
    from source_lab.paths import Paths

    paths = Paths.from_env()
    if command in ("status", "doctor", "preflight"):
        if args not in ([], ["--json"]):
            print("Usage: labctl source status|doctor [--json]", file=sys.stderr)
            return 2
        report = status()
        if args:
            print(json.dumps(report, indent=2))
        else:
            print(f"Source Lab: {report['state']} (Python {report['python']['version']})")
            print(f"Storage: {paths.storage} ({'writable' if report['storage']['writable'] else 'not writable'})")
            for tool, present in report["optional"].items():
                print(f"Optional {tool}: {'available' if present else 'not installed'}")
        return 0 if report["state"] == "ready" else 1
    if command == "setup":
        if args:
            print("Usage: labctl source setup", file=sys.stderr)
            return 2
        paths.prepare()
        print(f"Prepared local storage: {paths.storage}")
        return 0
    # Keep each engine invocation in this process, isolated from the console and
    # Android's modules. No shell evaluation or imports into the host server.
    commands = {
        "contracts": ("source_lab.contracts", []),
        "detect": ("source_lab.cli.run_detection", []),
        "map": ("source_lab.sourcemap", []),
        "crawl": ("source_lab.pipeline.ext_repo_analyzer", ["--out-dir", str(paths.analysis), "--workspace", str(paths.workspace)]),
        "merge": ("source_lab.pipeline.ext_merger", ["--analysis-dir", str(paths.analysis), "--workspace", str(paths.workspace), "--out", str(paths.storage / "merged")]),
        "merge-csvs": ("source_lab.pipeline.merge_csvs", []),
        "import-legacy": ("source_lab.import_legacy", []),
    }
    if command not in commands:
        print(f"Unsupported Source Lab command: {command}. Run labctl source --help.", file=sys.stderr)
        return 2
    module, defaults = commands[command]
    sys.argv = [module, *defaults, *args]
    runpy.run_module(module, run_name="__main__", alter_sys=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Source Lab: {exc}", file=sys.stderr)
        raise SystemExit(1)

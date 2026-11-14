#!/usr/bin/env python3
"""Verify Source Lab provenance and excluded files before a public commit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    manifest = json.loads((ROOT / "source-lab/PROVENANCE.json").read_text())
    problems = []
    for record in manifest["files"]:
        path = ROOT / record["destination"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["local_sha256"]:
            problems.append(f"Provenance hash mismatch: {record['destination']}")
    tracked = subprocess.check_output(["git", "ls-files", "-z", "source-lab"], cwd=ROOT).decode().split("\0")
    blocked_suffixes = {".apk", ".ipa", ".aab", ".exe", ".dll", ".so", ".dylib", ".zip", ".db", ".sqlite", ".xlsx", ".pdf"}
    for name in filter(None, tracked):
        path = ROOT / name
        parts = Path(name).parts
        if ("resources" in parts or "node_modules" in parts or ".git" in parts
                or path.suffix.lower() in blocked_suffixes or path.name == ".env"
                or ("storage" in parts and path.name != ".gitkeep")):
            problems.append(f"Excluded content is tracked: {name}")
        elif path.is_file() and b"\0" in path.read_bytes():
            problems.append(f"Binary content is tracked: {name}")
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print(f"Source import checks passed: {len(manifest['files'])} provenance entries; no excluded assets tracked.")
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())

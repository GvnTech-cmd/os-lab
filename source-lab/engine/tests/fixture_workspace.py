"""Generate owned, offline workspace scenarios; never commit generated outputs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ENGINE = Path(__file__).resolve().parents[1]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from source_lab.cli.run_detection import main as detect
from source_lab.evidence.schema import PlatformType, TargetIdentity
from source_lab.evidence.session import CollectorMetadata, SessionBundleWriter, SessionMetadata, SessionScope
from source_lab.sourcemap import RepoMap
from source_lab.sourcemap.report import to_json

FIXTURES = Path(__file__).parent / "fixtures/injection"


def build_workspace(root: Path, signing_key: bytes) -> dict:
    """Build a fresh detection/crawler/merge/map/session/UI workspace offline."""
    root = Path(root).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    targets = root / "targets"
    targets.mkdir()
    target = targets / "sample"
    shutil.copytree(FIXTURES / "browser_clean", target)
    output = root / "analysis/fixture__sample"
    if detect([str(target), "-o", str(output)]) != 0:
        raise RuntimeError("Fixture detection failed")
    (output / "repo-map.json").write_text(to_json(RepoMap().generate(target)))
    session_id = "ses_fixture_synthetic"
    metadata = SessionMetadata(
        session_id=session_id, platform=PlatformType.BROWSER_EXTENSION,
        target=TargetIdentity(identifier="sample"),
        collector=CollectorMetadata(engine="fixture-generator", profile_mode="synthetic"),
        scope=SessionScope(test_url="https://example.test"),
        limitations=["Synthetic test fixture; no browser behavior was observed."],
    )
    writer = SessionBundleWriter(output / "runtime-sessions" / session_id, metadata, hmac_key=signing_key)
    writer.append_event(0, "session_start", {"synthetic": True})
    writer.append_event(1, "session_complete", {"synthetic": True})
    writer.close()
    env = {**os.environ, "SOURCE_LAB_STORAGE": str(root)}
    runner = ENGINE.parent / "run.py"
    shutil.copytree(target, root / "cloned-repos/local__sample")
    for args in (
        ["crawl", str(target), "--no-metadata", "--no-ast", "--no-color", "--keep-workspace"],
        ["merge", "--plan", "--no-clone"],
        ["merge", "--no-clone", "--name", "Synthetic fixture"],
    ):
        result = subprocess.run([sys.executable, str(runner), *args], env=env,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f"Fixture {args[0]} failed: {result.stdout}\n{result.stderr}")
    ui = {"synthetic": True, "target": "fixture__sample", "session": session_id,
          "analysis": json.loads((output / "analysis-v2.json").read_text())}
    (root / "ui-fixture.json").write_text(json.dumps(ui, indent=2) + "\n")
    manifest = {
        "synthetic": True,
        "source": "owned browser_clean fixture; generated reports and session",
        "files": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(root.rglob("*")) if p.is_file()},
    }
    (root / "fixture-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"root": root, "output": output, "session": output / "runtime-sessions" / session_id,
            "manifest": manifest}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="New directory for generated fixtures")
    args = parser.parse_args()
    # Test callers supply an ephemeral key over stdin, never through argv or files.
    build_workspace(args.root, bytes.fromhex(sys.stdin.read().strip()))

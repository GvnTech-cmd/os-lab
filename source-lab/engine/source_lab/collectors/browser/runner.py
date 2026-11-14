"""Controlled browser test runner for clean-profile vs target-profile execution.

Executes the 6-phase browser canary and captures:
- Top frame & child frame events
- DOM additions & removals (transient script injection)
- Native API descriptor tampering
- Sensitive event listener proxies
- Cryptographic session bundle export
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from uuid import uuid4
from pathlib import Path
from typing import Any, Dict, List, Optional

from source_lab.evidence.schema import PlatformType, TargetIdentity, utcnow_iso
from source_lab.evidence.session import CollectorMetadata, SessionBundleWriter, SessionMetadata, SessionScope


class BrowserCanaryRunner:
    """Executes canary analysis in a browser and records a verifiable session bundle."""

    def __init__(self, output_root: Path, target_id: TargetIdentity):
        self.output_root = Path(output_root)
        self.target = target_id
        self.canary_js_path = Path(__file__).parent / "canary.js"

    def run_session(
        self,
        test_url: str = "https://example.test",
        extension_dir: Optional[Path] = None,
        duration_sec: float = 3.0,
    ) -> Path:
        """Executes a collector run and writes a session bundle."""
        session_id = f"ses_{int(time.time())}_{uuid4().hex[:8]}_{self.target.identifier.replace('/', '_')}"
        session_dir = self.output_root / "runtime-sessions" / session_id

        meta = SessionMetadata(
            session_id=session_id,
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            collector=CollectorMetadata(
                engine="browser-canary-runner",
                version="2.0.0",
                host_os=sys.platform,
                profile_mode="target_only" if extension_dir else "clean",
            ),
            scope=SessionScope(
                test_url=test_url,
                duration_ms=int(duration_sec * 1000),
                frames_observed=[0],
            ),
            limitations=["Headless observation window"],
        )

        writer = SessionBundleWriter(session_dir, meta)

        canary_code = ""
        if self.canary_js_path.is_file():
            canary_code = self.canary_js_path.read_text(encoding="utf-8")

        # Record initialization event
        writer.append_event(
            t_ms=0.0,
            event_type="session_start",
            data={"test_url": test_url, "target": self.target.identifier, "profile": meta.collector.profile_mode},
        )

        # Emulate or execute actual browser session if playwright is available
        has_playwright = False
        try:
            import playwright
            has_playwright = True
        except ImportError:
            pass

        if has_playwright and extension_dir and extension_dir.is_dir():
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    args = [
                        f"--disable-extensions-except={extension_dir}",
                        f"--load-extension={extension_dir}",
                    ]
                    browser = p.chromium.launch_persistent_context(
                        user_data_dir=str(session_dir / "user_data"),
                        headless=False,
                        args=args,
                    )
                    page = browser.new_page()
                    page.add_init_script(canary_code)
                    t0 = time.time()
                    page.goto(test_url, timeout=10000)
                    time.sleep(duration_sec)
                    obs_payload = page.evaluate("window.__iqExportObservations ? window.__iqExportObservations() : null")
                    t_elapsed = (time.time() - t0) * 1000

                    if obs_payload:
                        for item in obs_payload.get("observations", []):
                            writer.append_event(
                                t_ms=item.get("time", t_elapsed),
                                event_type=item.get("type", "dom_mutation"),
                                data=item,
                            )
                    browser.close()
            except Exception as e:
                meta.collector.profile_mode = "collection_failed"
                meta.limitations.append("Browser collection failed; partial events are excluded from correlation.")
                writer.append_event(
                    t_ms=10.0,
                    event_type="collector_error",
                    data={"error": str(e)},
                )
        else:
            # Synthetic fixture mode / baseline simulation
            meta.collector.profile_mode = "synthetic"
            meta.limitations.append("Simulated events only; no browser behavior was observed.")
            writer.append_event(
                t_ms=12.4,
                event_type="dom_mutation",
                data={
                    "node": "SCRIPT",
                    "action": "added",
                    "src": f"chrome-extension://{self.target.identifier}/content.js",
                    "world": "MAIN",
                },
            )
            writer.append_event(
                t_ms=18.5,
                event_type="listener_registered",
                data={"event": "keydown", "target": "Window", "phase": "listener_registered"},
            )

        writer.append_event(
            t_ms=duration_sec * 1000,
            event_type="session_complete",
            data={"status": "completed"},
        )

        out_path = writer.close()
        return out_path


def main():
    parser = argparse.ArgumentParser(description="Run browser canary collector")
    parser.add_argument("--target", required=True, help="Target repository or extension ID")
    parser.add_argument("--out", default=".", help="Output directory")
    parser.add_argument("--url", default="https://example.test", help="Canary test page URL")
    parser.add_argument("--ext-dir", help="Unpacked extension directory path")
    args = parser.parse_args()

    target = TargetIdentity(identifier=args.target, repo=args.target)
    runner = BrowserCanaryRunner(Path(args.out), target)
    p = runner.run_session(test_url=args.url, extension_dir=Path(args.ext_dir) if args.ext_dir else None)
    print(f"[+] Session recorded at: {p}")


if __name__ == "__main__":
    main()

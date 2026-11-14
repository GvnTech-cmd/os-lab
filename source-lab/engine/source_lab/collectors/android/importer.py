"""Android telemetry importer and session bundle builder.

Transforms:
- /proc/self/maps dumps (frida-agent, liblsposed, anonymous r-xp/rwxp regions)
- Thread lists (gmain, gum-js-loop, pool-frida)
- Logcat entries (WebView console, Xposed logs)
into standardized runtime session bundles.
"""

from __future__ import annotations

import json
import time
from uuid import uuid4
from pathlib import Path
from typing import Any, Dict, List, Optional

from source_lab.evidence.schema import PlatformType, TargetIdentity
from source_lab.evidence.session import (
    CollectorMetadata,
    SessionBundleWriter,
    SessionMetadata,
    SessionScope,
)


class AndroidTelemetryImporter:
    """Imports Android telemetry into standard V2 runtime session bundles."""

    def __init__(self, output_root: Path, target: TargetIdentity):
        self.output_root = Path(output_root)
        self.target = target

    def import_session(
        self,
        maps_lines: Optional[List[str]] = None,
        threads: Optional[List[str]] = None,
        logcat_entries: Optional[List[str]] = None,
        session_id_suffix: str = "andr",
        *, synthetic: bool = False,
    ) -> Path:
        session_id = f"ses_{int(time.time())}_{uuid4().hex[:8]}_{session_id_suffix}"
        session_dir = self.output_root / "runtime-sessions" / session_id

        meta = SessionMetadata(
            session_id=session_id,
            platform=PlatformType.ANDROID_APP,
            target=self.target,
            collector=CollectorMetadata(
                engine="android-telemetry-importer",
                version="2.0.0",
                host_os="android",
                profile_mode="synthetic" if synthetic else "target_isolated",
            ),
            limitations=["Imported operator telemetry; no native collector was launched."] +
                         (["Simulated events only; excluded from runtime correlation."] if synthetic else []),
            scope=SessionScope(
                package_name=self.target.package_name or self.target.identifier,
                duration_ms=5000,
            ),
        )

        writer = SessionBundleWriter(session_dir, meta)
        t_ms = 0.0

        writer.append_event(
            t_ms=t_ms,
            event_type="session_start",
            data={"target": self.target.identifier, "os": "android"},
        )

        # Parse /proc/self/maps
        if maps_lines:
            for line in maps_lines:
                t_ms += 2.0
                parts = line.split()
                if len(parts) >= 2:
                    perms = parts[1]
                    pathname = parts[-1] if len(parts) >= 6 else ""

                    # Flag anonymous executable pages
                    if "x" in perms and (not pathname or pathname.startswith("[anon")):
                        writer.append_event(
                            t_ms=t_ms,
                            event_type="unbacked_exec_mapping",
                            data={"permissions": perms, "range": parts[0], "path": pathname},
                        )

                    # Flag foreign hooking libraries
                    if any(sig in pathname for sig in ("frida", "lsposed", "xposed", "substrate")):
                        writer.append_event(
                            t_ms=t_ms,
                            event_type="hook_library_mapped",
                            data={"path": pathname, "permissions": perms},
                        )

        # Parse threads
        if threads:
            for th in threads:
                t_ms += 5.0
                if any(sig in th.lower() for sig in ("gum-js", "frida", "gmain")):
                    writer.append_event(
                        t_ms=t_ms,
                        event_type="instrumentation_thread",
                        data={"thread_name": th},
                    )

        # Parse logcat entries
        if logcat_entries:
            for log in logcat_entries:
                t_ms += 10.0
                if any(sig in log for sig in ("addJavascriptInterface", "WebView", "Xposed")):
                    writer.append_event(
                        t_ms=t_ms,
                        event_type="logcat_event",
                        data={"message": log.strip()[:200]},
                    )

        writer.append_event(t_ms=t_ms + 10.0, event_type="session_complete", data={})
        return writer.finalize()

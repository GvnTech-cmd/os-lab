"""iOS telemetry importer and session bundle builder.

Transforms:
- MobileSubstrate / ElleKit / Frida dynamic image probe outputs
- ARM64 prologue trampoline inspection
- WKWebView honeypot observations
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


class IOSTelemetryImporter:
    """Imports iOS telemetry into standard V2 runtime session bundles."""

    def __init__(self, output_root: Path, target: TargetIdentity):
        self.output_root = Path(output_root)
        self.target = target

    def import_session(
        self,
        loaded_dylibs: Optional[List[str]] = None,
        trampolines: Optional[List[Dict[str, Any]]] = None,
        wk_events: Optional[List[Dict[str, Any]]] = None,
        session_id_suffix: str = "ios",
        *, synthetic: bool = False,
    ) -> Path:
        session_id = f"ses_{int(time.time())}_{uuid4().hex[:8]}_{session_id_suffix}"
        session_dir = self.output_root / "runtime-sessions" / session_id

        meta = SessionMetadata(
            session_id=session_id,
            platform=PlatformType.IOS_APP,
            target=self.target,
            collector=CollectorMetadata(
                engine="ios-telemetry-importer",
                version="2.0.0",
                host_os="ios",
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
            data={"target": self.target.identifier, "os": "ios"},
        )

        if loaded_dylibs:
            for dylib in loaded_dylibs:
                t_ms += 5.0
                if any(sig in dylib for sig in ("Substrate", "ElleKit", "Frida", "libhooker", "Substitute")):
                    writer.append_event(
                        t_ms=t_ms,
                        event_type="tweak_framework_detected",
                        data={"dylib_path": dylib},
                    )

        if trampolines:
            for tr in trampolines:
                t_ms += 10.0
                writer.append_event(
                    t_ms=t_ms,
                    event_type="arm64_trampoline",
                    data={
                        "symbol": tr.get("symbol"),
                        "address": tr.get("address"),
                        "prologue_bytes": tr.get("bytes"),
                        "instruction": tr.get("instruction", "B / BR X16"),
                    },
                )

        if wk_events:
            for ev in wk_events:
                t_ms += 15.0
                writer.append_event(
                    t_ms=t_ms,
                    event_type="wkwebview_message",
                    data=ev,
                )

        writer.append_event(t_ms=t_ms + 10.0, event_type="session_complete", data={})
        return writer.finalize()

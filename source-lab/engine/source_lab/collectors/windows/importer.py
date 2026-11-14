"""Windows telemetry importer and session bundle builder.

Transforms:
- PE-sieve JSON output (hooked exports, replaced modules, unbacked code)
- Sysmon / ETW events (CreateRemoteThread, ProcessAccess, ProcessTampering)
into standardized runtime session bundles.
"""

from __future__ import annotations

import json
import sys
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


class WindowsTelemetryImporter:
    """Imports Windows telemetry into standard V2 runtime session bundles."""

    def __init__(self, output_root: Path, target: TargetIdentity):
        self.output_root = Path(output_root)
        self.target = target

    def import_session(
        self,
        pe_sieve_data: Optional[Dict[str, Any]] = None,
        etw_events: Optional[List[Dict[str, Any]]] = None,
        session_id_suffix: str = "win",
        *, synthetic: bool = False,
    ) -> Path:
        session_id = f"ses_{int(time.time())}_{uuid4().hex[:8]}_{session_id_suffix}"
        session_dir = self.output_root / "runtime-sessions" / session_id

        meta = SessionMetadata(
            session_id=session_id,
            platform=PlatformType.WINDOWS_APP,
            target=self.target,
            collector=CollectorMetadata(
                engine="windows-telemetry-importer",
                version="2.0.0",
                host_os="windows",
                profile_mode="synthetic" if synthetic else "target_isolated",
            ),
            limitations=["Imported operator telemetry; no native collector was launched."] +
                         (["Simulated events only; excluded from runtime correlation."] if synthetic else []),
            scope=SessionScope(
                process_name=self.target.package_name or self.target.identifier,
                duration_ms=5000,
            ),
        )

        writer = SessionBundleWriter(session_dir, meta)
        t_ms = 0.0

        writer.append_event(
            t_ms=t_ms,
            event_type="session_start",
            data={"target": self.target.identifier, "os": "windows"},
        )

        # Parse PE-sieve JSON
        if pe_sieve_data:
            scanned = pe_sieve_data.get("scanned", {})
            hooks = pe_sieve_data.get("hooks", [])
            for h in hooks:
                t_ms += 15.0
                writer.append_event(
                    t_ms=t_ms,
                    event_type="memory_hook",
                    data={
                        "module": h.get("module"),
                        "function": h.get("function"),
                        "target_address": h.get("hooked_to"),
                        "hook_type": h.get("type", "detour_jump"),
                    },
                )
            if pe_sieve_data.get("unbacked_exec"):
                t_ms += 10.0
                writer.append_event(
                    t_ms=t_ms,
                    event_type="unbacked_exec",
                    data={
                        "regions": pe_sieve_data.get("unbacked_regions", []),
                        "count": len(pe_sieve_data.get("unbacked_regions", [])),
                    },
                )

        # Parse ETW / Sysmon events
        if etw_events:
            for ev in etw_events:
                t_ms += 20.0
                ev_id = ev.get("EventID") or ev.get("id")
                data = ev.get("Data", ev)
                if ev_id in (8, "8"):  # CreateRemoteThread
                    writer.append_event(
                        t_ms=t_ms,
                        event_type="remote_thread",
                        data={
                            "source_image": data.get("SourceImage"),
                            "target_image": data.get("TargetImage"),
                            "start_address": data.get("StartAddress"),
                        },
                    )
                elif ev_id in (25, "25"):  # ProcessTampering
                    writer.append_event(
                        t_ms=t_ms,
                        event_type="process_tampering",
                        data={
                            "type": data.get("Type", "process_hollowing"),
                            "image": data.get("TargetImage"),
                        },
                    )
                else:
                    writer.append_event(t_ms=t_ms, event_type="etw_event", data=data)

        writer.append_event(t_ms=t_ms + 10.0, event_type="session_complete", data={})
        return writer.finalize()

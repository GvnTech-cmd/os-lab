"""macOS telemetry importer and session bundle builder.

Transforms:
- dyld image lists & dladdr symbol verification
- Endpoint Security events (DYLD_INSERT_LIBRARIES, task_for_pid)
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


class MacOSTelemetryImporter:
    """Imports macOS telemetry into standard V2 runtime session bundles."""

    def __init__(self, output_root: Path, target: TargetIdentity):
        self.output_root = Path(output_root)
        self.target = target

    def import_session(
        self,
        dyld_images: Optional[List[str]] = None,
        swizzled_methods: Optional[List[Dict[str, str]]] = None,
        es_events: Optional[List[Dict[str, Any]]] = None,
        session_id_suffix: str = "mac",
        *, synthetic: bool = False,
    ) -> Path:
        session_id = f"ses_{int(time.time())}_{uuid4().hex[:8]}_{session_id_suffix}"
        session_dir = self.output_root / "runtime-sessions" / session_id

        meta = SessionMetadata(
            session_id=session_id,
            platform=PlatformType.MACOS_APP,
            target=self.target,
            collector=CollectorMetadata(
                engine="macos-telemetry-importer",
                version="2.0.0",
                host_os="darwin",
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
            data={"target": self.target.identifier, "os": "darwin"},
        )

        if dyld_images:
            for img in dyld_images:
                t_ms += 5.0
                is_system = img.startswith(("/System/Library/", "/usr/lib/"))
                if not is_system:
                    writer.append_event(
                        t_ms=t_ms,
                        event_type="foreign_image_mapped",
                        data={"path": img, "is_system": False},
                    )

        if swizzled_methods:
            for sw in swizzled_methods:
                t_ms += 10.0
                writer.append_event(
                    t_ms=t_ms,
                    event_type="objc_swizzle",
                    data={
                        "class": sw.get("class"),
                        "selector": sw.get("selector"),
                        "original_imp": sw.get("original_imp"),
                        "new_imp": sw.get("new_imp"),
                    },
                )

        if es_events:
            for es in es_events:
                t_ms += 15.0
                writer.append_event(
                    t_ms=t_ms,
                    event_type="endpoint_security_event",
                    data=es,
                )

        writer.append_event(t_ms=t_ms + 10.0, event_type="session_complete", data={})
        return writer.finalize()

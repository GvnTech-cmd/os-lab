"""Runtime session bundle reader, writer, and cryptographic integrity validator.

Directory structure:
  runtime-sessions/<session-id>/
    session.json
    events.jsonl
    manifest.json
    manifest.sig
    artifacts/
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .schema import PlatformType, TargetIdentity, utcnow_iso

MIN_HMAC_KEY_BYTES = 32
ENV_HMAC_KEY = "IQ_SESSION_HMAC_KEY"
ENV_HMAC_KEY_FILE = "IQ_SESSION_HMAC_KEY_FILE"


class SessionKeyError(RuntimeError):
    """Raised when the session HMAC key is missing, ambiguous or too short."""


def _validate_key(raw: bytes, source: str) -> bytes:
    if len(raw) < MIN_HMAC_KEY_BYTES:
        raise SessionKeyError(
            f"Session HMAC key from {source} must be at least {MIN_HMAC_KEY_BYTES} bytes; got {len(raw)}."
        )
    return raw


# @lat: [[source-lab#Runtime evidence]]
def load_hmac_key() -> bytes:
    """Resolves the session HMAC key from the environment or a key file."""
    env_value = os.environ.get(ENV_HMAC_KEY)
    file_value = os.environ.get(ENV_HMAC_KEY_FILE)

    env_key: Optional[bytes] = None
    file_key: Optional[bytes] = None

    if env_value is not None:
        env_key = _validate_key(env_value.encode("utf-8"), ENV_HMAC_KEY)
    if file_value:
        key_path = Path(file_value)
        try:
            info = key_path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise OSError("Linked key file")
            fd = os.open(key_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise OSError("Key must be a regular file")
                raw = stream.read(4097)
            if len(raw) > 4096:
                raise SessionKeyError("Session key exceeds the size limit")
        except OSError:
            raise SessionKeyError(f"Cannot read {ENV_HMAC_KEY_FILE}") from None
        if raw.endswith(b"\r\n"):
            raw = raw[:-2]
        elif raw.endswith(b"\n"):
            raw = raw[:-1]
        try:
            mode = stat.S_IMODE(key_path.stat().st_mode)
            if mode & 0o077:
                print(
                    f"[!] Warning: {key_path} has mode {oct(mode)}; restrict it to 0600.",
                    file=sys.stderr,
                )
        except OSError:
            pass
        file_key = _validate_key(raw, str(key_path))

    if env_key is not None and file_key is not None:
        if not hmac.compare_digest(env_key, file_key):
            raise SessionKeyError(
                f"{ENV_HMAC_KEY} and {ENV_HMAC_KEY_FILE} specify different keys."
            )
        return env_key
    if env_key is not None:
        return env_key
    if file_key is not None:
        return file_key
    raise SessionKeyError(
        f"No session HMAC key configured. Set {ENV_HMAC_KEY} or {ENV_HMAC_KEY_FILE}."
    )



@dataclass
class CollectorMetadata:
    engine: str
    version: str = "2.0.0"
    host_os: str = "unknown"
    browser_version: Optional[str] = None
    profile_mode: str = "target_only"  # clean, target_only, clean_vs_target
    baseline_session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CollectorMetadata:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SessionScope:
    test_url: Optional[str] = None
    duration_ms: int = 5000
    frames_observed: List[int] = field(default_factory=lambda: [0])
    process_name: Optional[str] = None
    package_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SessionScope:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SessionMetadata:
    session_id: str
    platform: PlatformType
    target: TargetIdentity
    collector: CollectorMetadata
    scope: SessionScope
    limitations: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utcnow_iso)
    schema_version: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "platform": self.platform.value if isinstance(self.platform, PlatformType) else self.platform,
            "target": self.target.to_dict() if hasattr(self.target, "to_dict") else self.target,
            "collector": self.collector.to_dict() if hasattr(self.collector, "to_dict") else self.collector,
            "scope": self.scope.to_dict() if hasattr(self.scope, "to_dict") else self.scope,
            "limitations": self.limitations,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SessionMetadata:
        return cls(
            schema_version=data.get("schema_version", 2),
            session_id=data["session_id"],
            created_at=data.get("created_at", utcnow_iso()),
            platform=PlatformType(data["platform"]),
            target=TargetIdentity.from_dict(data.get("target", {})),
            collector=CollectorMetadata.from_dict(data.get("collector", {})),
            scope=SessionScope.from_dict(data.get("scope", {})),
            limitations=data.get("limitations", []),
        )


class SessionBundleWriter:
    """Creates and cryptographically signs a runtime session bundle."""

    def __init__(self, session_dir: Path, session_meta: SessionMetadata, hmac_key: Optional[bytes] = None):
        self.hmac_key = load_hmac_key() if hmac_key is None else _validate_key(hmac_key, "explicit hmac_key")
        self.session_dir = Path(session_dir)
        if self.session_dir.exists():
            raise FileExistsError(f"Session directory already exists: {self.session_dir}")
        self.session_dir.mkdir(parents=True, exist_ok=False)
        self.artifacts_dir = self.session_dir / "artifacts"
        self.artifacts_dir.mkdir(exist_ok=True)
        self.meta = session_meta
        self.events_file = self.session_dir / "events.jsonl"
        self.events_handle = open(self.events_file, "a", encoding="utf-8")
        self.event_seq = 0

    def append_event(self, t_ms: float, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        self.event_seq += 1
        record = {
            "seq": self.event_seq,
            "t_ms": round(t_ms, 2),
            "type": event_type,
            "data": data,
        }
        self.events_handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        self.events_handle.flush()
        return record

    def save_artifact(self, content: bytes, ext: str) -> str:
        sha = hashlib.sha256(content).hexdigest()
        artifact_file = self.artifacts_dir / f"{sha}{ext}"
        artifact_file.write_bytes(content)
        return sha

    # @lat: [[source-lab#Runtime evidence]]
    def close(self) -> Path:
        self.events_handle.close()

        # Write session.json
        meta_file = self.session_dir / "session.json"
        meta_file.write_text(json.dumps(self.meta.to_dict(), indent=2), encoding="utf-8")

        # Build cryptographic manifest
        manifest: Dict[str, str] = {}
        for p in self.session_dir.rglob("*"):
            if p.is_file() and p.name not in ("manifest.json", "manifest.sig"):
                rel = str(p.relative_to(self.session_dir))
                manifest[rel] = hashlib.sha256(p.read_bytes()).hexdigest()

        manifest_file = self.session_dir / "manifest.json"
        manifest_data = json.dumps(manifest, indent=2, sort_keys=True)
        manifest_file.write_text(manifest_data, encoding="utf-8", newline="\n")

        # Sign manifest
        sig = hmac.new(self.hmac_key, manifest_data.encode("utf-8"), hashlib.sha256).hexdigest()
        sig_file = self.session_dir / "manifest.sig"
        sig_file.write_text(sig, encoding="utf-8")

        return self.session_dir

    def finalize(self) -> Path:
        return self.close()


class SessionBundleReader:
    """Reads and validates an imported session bundle."""

    def __init__(self, session_dir: Path, hmac_key: Optional[bytes] = None):
        self.session_dir = Path(session_dir)
        self.hmac_key = load_hmac_key() if hmac_key is None else _validate_key(hmac_key, "explicit hmac_key")
        if not self.session_dir.is_dir():
            raise FileNotFoundError(f"Session directory not found: {session_dir}")

    def verify_integrity(self) -> Dict[str, Any]:
        """Checks hashes and signature; returns validation results."""
        # The manifest is untrusted until authenticated. Never follow its paths
        # outside this bundle, and require signatures to cover correlation inputs.
        failure = {"valid": False, "signature_verified": False, "mismatches": [], "file_count": 0}
        try:
            total = 0
            def read(relative: str, cap: int = 5 * 1024 * 1024) -> bytes:
                nonlocal total
                parts = relative.replace("\\", "/").split("/")
                if not parts or any(not part or part in (".", "..") or ":" in part for part in parts):
                    raise ValueError("Invalid manifest path")
                path = self.session_dir
                if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                    raise ValueError("Linked bundle")
                for part in parts:
                    path = path / part
                    if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                        raise ValueError("Linked bundle member")
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError("Nonregular bundle member")
                    data = stream.read(cap + 1)
                total += len(data)
                if len(data) > cap or total > 16 * 1024 * 1024:
                    raise ValueError("Bundle exceeds verification limit")
                return data
            content = read("manifest.json")
            manifest = json.loads(content)
            if (not isinstance(manifest, dict) or not {"session.json", "events.jsonl"} <= manifest.keys()
                    or len(manifest) > 1000):
                raise ValueError("Manifest must cover session.json and events.jsonl")
            signature = read("manifest.sig", 128).decode("ascii").strip()
            signature_valid = hmac.compare_digest(signature, hmac.new(self.hmac_key, content, hashlib.sha256).hexdigest())
            # Legacy Windows writers signed LF text before write_text emitted CRLF.
            # JSON whitespace canonicalization preserves those existing bundles.
            if not signature_valid and b"\r\n" in content:
                canonical = content.replace(b"\r\n", b"\n")
                signature_valid = hmac.compare_digest(signature, hmac.new(self.hmac_key, canonical, hashlib.sha256).hexdigest())
            if not signature_valid:
                return {**failure, "error": "Manifest signature not verified"}
            mismatches = []
            for relative, expected in manifest.items():
                if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                    raise ValueError("Invalid manifest hash")
                if hashlib.sha256(read(relative)).hexdigest() != expected:
                    mismatches.append("Hash mismatch on " + relative)
            return {"valid": not mismatches, "signature_verified": True,
                    "mismatches": mismatches, "file_count": len(manifest)}
        except (OSError, ValueError, UnicodeError, TypeError, RecursionError):
            return {**failure, "error": "Missing, invalid or unsafe signed session bundle"}

    def get_metadata(self) -> SessionMetadata:
        meta_file = self.session_dir / "session.json"
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        return SessionMetadata.from_dict(data)

    def iter_events(self) -> Iterator[Dict[str, Any]]:
        events_file = self.session_dir / "events.jsonl"
        if not events_file.exists():
            return
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def read_events(self) -> List[Dict[str, Any]]:
        return list(self.iter_events())

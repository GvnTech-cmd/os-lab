"""Portable resource and mutable-state roots for Source Lab."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    storage: Path
    resources: Path

    @classmethod
    def from_env(cls) -> Paths:
        storage = Path(os.environ.get("SOURCE_LAB_STORAGE", str(LAB_ROOT / "storage"))).expanduser().resolve()
        resources = Path(os.environ.get("SOURCE_LAB_RESOURCES", str(storage / "resources"))).expanduser().resolve()
        return cls(storage=storage, resources=resources)

    @property
    def analysis(self) -> Path:
        return self.storage / "analysis"

    @property
    def sources(self) -> Path:
        return self.resources / "sources"

    @property
    def workspace(self) -> Path:
        return self.storage / "cloned-repos"

    def prepare(self) -> None:
        """Create writable state only; external resources are never modified."""
        for folder in (self.storage, self.analysis, self.workspace,
                       self.storage / "targets", self.storage / "merged", self.storage / "catalogs"):
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)

"""Cleaned-items ledger, learned profile, soft pre-selection, Quick Clean (CLN-26).

The loop: every item the user actually cleaned is recorded locally; repeated,
user-driven cleans of the same *kind* of thing (same category, detector and
basename, e.g. ``node_modules``) build a scored profile; the profile then

* soft-pre-selects matching rows in the next scan (``selected``, never
  ``default_selected``, and never a high-risk, credential or privacy row), and
* seeds a Quick Clean: re-measure only the learned paths that still exist,
  instead of a full scan.

Nothing here deletes. Pre-selection only ticks a box; the plan → confirm →
clean flow (CLN-13) still shows and validates every row.

Score = ``frequency × 0.5 ** (age_days / half_life) × average_bytes × (1 + user_chosen_share)``

Fixes against the private implementation this was ported from:

* an unreadable ledger file was silently treated as empty and overwritten on the
  next write, losing the lifetime totals; here it is moved aside to
  ``<name>.corrupt-<epoch>`` and reported through :attr:`LedgerStore.recovered_from`;
* pre-selection excluded only ``high`` risk; os-lab safety rule 5 also excludes
  the ``credentials`` and ``privacy`` classes.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field

DEFAULT_RETENTION_DAYS = 90
DEFAULT_HALF_LIFE_DAYS = 30.0
DEFAULT_MIN_FREQUENCY = 3
DEFAULT_MIN_USER_CHOSEN_SHARE = 0.75
EXCLUDED_RISKS = frozenset({"high", "credentials", "privacy"})


@dataclass(frozen=True)
class CleanedItem:
    path: str
    name: str
    category: str
    detection_source: str
    size_freed: int
    #: True when the user cleaned something the detector did NOT pre-select (strong intent).
    user_chosen: bool
    cleaned_at: float = field(default_factory=time.time)
    platform: str = sys.platform
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def make(cls, *, path: str, name: str, category: str, detection_source: str, size_freed: int,
             default_selected: bool, at: float | None = None) -> CleanedItem:
        """Build a row from one *successful* clean result (bytes actually freed, CLN-13)."""
        return cls(path=os.path.normpath(path) if path else "", name=name, category=category,
                   detection_source=detection_source, size_freed=max(0, int(size_freed)),
                   user_chosen=not default_selected, cleaned_at=time.time() if at is None else at)


@dataclass(frozen=True)
class Summary:
    lifetime_count: int
    lifetime_bytes: int
    window_count: int
    window_bytes: int


class LedgerStore:
    """Single JSON file in private state; raw rows pruned to a retention window, lifetime totals kept."""

    def __init__(self, path: str, *, retention_days: int = DEFAULT_RETENTION_DAYS,
                 clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self.retention = retention_days * 86_400
        self.clock = clock
        self.recovered_from: str | None = None
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or not isinstance(data.get("items", []), list):
                raise ValueError("unexpected ledger shape")
            return data
        except FileNotFoundError:
            return {"items": [], "lifetime_count": 0, "lifetime_bytes": 0}
        except (OSError, ValueError):
            aside = f"{self.path}.corrupt-{int(self.clock())}"
            try:
                os.replace(self.path, aside)
                self.recovered_from = aside
            except OSError:
                pass
            return {"items": [], "lifetime_count": 0, "lifetime_bytes": 0}

    def _save(self, data: dict) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".ledger-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _prune(self, data: dict) -> None:
        cutoff = self.clock() - self.retention
        data["items"] = [i for i in data["items"] if i.get("cleaned_at", 0) >= cutoff]

    def record(self, item: CleanedItem) -> None:
        with self._lock:
            data = self._load()
            data["items"].append(asdict(item))
            data["lifetime_count"] = int(data.get("lifetime_count", 0)) + 1
            data["lifetime_bytes"] = int(data.get("lifetime_bytes", 0)) + item.size_freed
            self._prune(data)
            self._save(data)

    def recent_items(self) -> list[CleanedItem]:
        with self._lock:
            data = self._load()
        self._prune(data)
        rows = [CleanedItem(**i) for i in data["items"]]
        return sorted(rows, key=lambda r: r.cleaned_at, reverse=True)

    def summary(self) -> Summary:
        with self._lock:
            data = self._load()
        self._prune(data)
        return Summary(int(data.get("lifetime_count", 0)), int(data.get("lifetime_bytes", 0)),
                       len(data["items"]), sum(int(i.get("size_freed", 0)) for i in data["items"]))


@dataclass(frozen=True, order=True)
class ProfileKey:
    category: str
    detection_source: str
    path_pattern: str


def key_for(category: str, detection_source: str, path: str, name: str) -> ProfileKey:
    """Group by basename so repeated cleans of the same kind of folder match wherever they live."""
    pattern = os.path.basename(os.path.normpath(path)) if path else name
    return ProfileKey(category, detection_source, pattern or name)


@dataclass(frozen=True)
class ProfileEntry:
    key: ProfileKey
    frequency: int
    total_bytes: int
    average_bytes: int
    last_cleaned_at: float
    user_chosen_share: float
    score: float


def build_profile(items: Iterable[CleanedItem], *, now: float | None = None,
                  half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> list[ProfileEntry]:
    """Aggregate and rank. Deterministic for a given ``now``."""
    now = time.time() if now is None else now
    half_life = max(half_life_days, 1e-4)
    groups: dict[ProfileKey, list[CleanedItem]] = {}
    for item in items:
        groups.setdefault(key_for(item.category, item.detection_source, item.path, item.name), []).append(item)
    entries = []
    for key, group in groups.items():
        freq = len(group)
        total = sum(i.size_freed for i in group)
        average = total / freq
        last = max(i.cleaned_at for i in group)
        share = sum(1 for i in group if i.user_chosen) / freq
        age_days = max(0.0, (now - last) / 86_400)
        score = freq * math.pow(0.5, age_days / half_life) * average * (1 + share)
        entries.append(ProfileEntry(key, freq, total, round(average), last, share, score))
    return sorted(entries, key=lambda e: (-e.score, -e.frequency, e.key))


def should_preselect(*, category: str, detection_source: str, path: str, name: str, risk: str | None,
                     already_default_selected: bool, profile: Sequence[ProfileEntry],
                     min_frequency: int = DEFAULT_MIN_FREQUENCY,
                     min_user_chosen_share: float = DEFAULT_MIN_USER_CHOSEN_SHARE) -> bool:
    if already_default_selected:
        return False
    if risk is not None and risk.lower() in EXCLUDED_RISKS:
        return False
    key = key_for(category, detection_source, path, name)
    entry = next((e for e in profile if e.key == key), None)
    return entry is not None and entry.frequency >= min_frequency and entry.user_chosen_share >= min_user_chosen_share


@dataclass(frozen=True)
class QuickCleanSeed:
    key: ProfileKey
    path: str
    score: float


def quick_clean_seeds(profile: Sequence[ProfileEntry], items: Iterable[CleanedItem], *, limit: int = 5,
                      path_exists: Callable[[str], bool] = os.path.lexists) -> list[QuickCleanSeed]:
    """Up to ``limit`` paths to re-measure: per top pattern, its most recent still-existing path.

    The caller re-validates each seed (path policy, catalog allowed roots) before
    measuring it; a seed is a hint, not an authorisation.
    """
    by_key: dict[ProfileKey, list[CleanedItem]] = {}
    for item in items:
        if item.path:
            by_key.setdefault(key_for(item.category, item.detection_source, item.path, item.name), []).append(item)
    seen: set[str] = set()
    seeds: list[QuickCleanSeed] = []
    for entry in profile:
        if len(seeds) >= limit:
            break
        for cand in sorted(by_key.get(entry.key, []), key=lambda i: i.cleaned_at, reverse=True):
            if cand.path not in seen and path_exists(cand.path):
                seen.add(cand.path)
                seeds.append(QuickCleanSeed(entry.key, cand.path, entry.score))
                break
    return seeds

"""Cleanup Lab reference logic.

Pure, standard-library-only building blocks contributed by the maintainer for
the Cleanup Lab roadmap (CLN-21 … CLN-29). Nothing in this package deletes,
moves or writes user files: it classifies, plans and scores. Destructive work
belongs to the engine's plan → confirm → clean flow (CLN-13), which must
re-validate every path it receives from here.

Modules
-------
- :mod:`cleanup_ref.path_policy` — canonical paths, protected roots, symlink-safe
  containment (CLN-12, CLN-21, CLN-23).
- :mod:`cleanup_ref.artifacts` — marker-verified project build-artifact
  signatures and a read-only sweep (CLN-24).
- :mod:`cleanup_ref.devcache` — where each developer tool really keeps its cache:
  environment, the tool's own answer (fixed argv, no shell), then per-OS default
  (CLN-25).
- :mod:`cleanup_ref.relocation` — link-status classifier and copy → verify →
  swap plans for moving a cache to another volume (CLN-27).
- :mod:`cleanup_ref.learning` — cleaned-items ledger, learned profile scoring,
  soft pre-selection and Quick Clean seeds (CLN-26).
"""

__all__ = ["artifacts", "devcache", "learning", "path_policy", "relocation"]

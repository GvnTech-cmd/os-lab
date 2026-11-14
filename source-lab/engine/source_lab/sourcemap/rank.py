"""Ranking: PageRank over the file graph, entrypoints and cycles."""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

DAMPING = 0.85
ITERATIONS = 20
ENTRYPOINT_CAP = 20
CYCLE_CAP = 20


def _imports_of(entry) -> list:
    if isinstance(entry, dict):
        return entry.get("imports") or []
    return entry.imports


def _edges(files: dict) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    outgoing: Dict[str, Set[str]] = {path: set() for path in files}
    incoming: Dict[str, Set[str]] = {path: set() for path in files}
    for path in sorted(files):
        for imp in _imports_of(files[path]):
            resolved = imp.get("resolved") if isinstance(imp, dict) else imp.resolved
            external = imp.get("external") if isinstance(imp, dict) else imp.external
            if resolved and not external and resolved in files and resolved != path:
                outgoing[path].add(resolved)
                incoming[resolved].add(path)
    return outgoing, incoming


def pagerank(files: dict) -> Dict[str, float]:
    if not files:
        return {}
    outgoing, _ = _edges(files)
    scores = {path: 1.0 / len(files) for path in files}
    for _ in range(ITERATIONS):
        base = (1.0 - DAMPING) / len(files)
        contributions: Dict[str, float] = {path: 0.0 for path in files}
        for path, targets in outgoing.items():
            if not targets:
                continue
            share = scores[path] / len(targets)
            for target in targets:
                contributions[target] += share
        dangling = sum(scores[path] for path, targets in outgoing.items() if not targets)
        dangling_share = dangling / len(files)
        scores = {path: base + DAMPING * (contributions[path] + dangling_share)
                  for path in files}
    total = sum(scores.values()) or 1.0
    return {path: score / total for path, score in scores.items()}


def entrypoints(files: dict, scores: Dict[str, float],
                explicit: Dict[str, str]) -> List[dict]:
    """Top files with no importers and at least one import, plus the explicit
    entrypoints (package.json main/preload, manifest launcher) with their own
    named reason."""
    outgoing, incoming = _edges(files)
    out: List[dict] = []
    seen = set()
    for path in sorted(explicit):
        if path in files:
            out.append({"path": path, "score": round(scores.get(path, 0.0), 6),
                        "reason": explicit[path]})
            seen.add(path)
    candidates = [path for path in sorted(files)
                  if path not in seen and not incoming[path] and outgoing[path]]
    candidates.sort(key=lambda p: (-scores.get(p, 0.0), p))
    for path in candidates:
        if len(out) >= ENTRYPOINT_CAP:
            break
        out.append({"path": path, "score": round(scores.get(path, 0.0), 6),
                    "reason": f"no importers, {len(outgoing[path])} imports"})
    return out[:ENTRYPOINT_CAP]


def cycles(files: dict) -> List[List[str]]:
    """Strongly connected components larger than one file (Tarjan, iterative)."""
    outgoing, _ = _edges(files)
    nodes = sorted(files)
    index: Dict[str, int] = {}
    low: Dict[str, int] = {}
    on_stack: Set[str] = set()
    stack: List[str] = []
    result: List[List[str]] = []
    counter = 0

    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(sorted(outgoing.get(root, ()))))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(outgoing.get(child, ())))))
                    advanced = True
                    break
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: List[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    component.sort()
                    # Legacy contract: a cycle repeats its first node so the
                    # path reads as a loop (["a.py", "b.py", "a.py"]).
                    result.append(component + [component[0]])
    ordered = sorted(result, key=lambda c: (-len(c), c))
    return [c for c in ordered[:CYCLE_CAP]]

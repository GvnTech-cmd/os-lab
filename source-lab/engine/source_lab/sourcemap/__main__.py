"""Standalone CLI for the repository map.

``python3 -m source_lab.sourcemap --root DIR --out FILE`` (the original form) and
``python3 -m source_lab.sourcemap generate --root DIR --out FILE`` are equivalent.
``query`` applies a filter to an existing artifact without rewriting it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .engine import RepoMap
from .filter import MapFilter
from .report import to_json, write


def _csv(values) -> tuple:
    if not values:
        return ()
    if isinstance(values, str):
        values = [values]
    out: List[str] = []
    for value in values:
        out.extend(item.strip() for item in value.split(",") if item.strip())
    return tuple(out)


def _filter(args) -> MapFilter:
    return MapFilter(
        kinds=_csv(args.kind),
        roles=_csv(args.role),
        langs=_csv(args.langs) if getattr(args, "langs", None) else (),
        paths=_csv(args.path),
        targets=_csv(args.target) or _csv(getattr(args, "map_target", None)),
        exported_only=args.exported_only,
        min_role_confidence=args.min_role_confidence,
    )


def _add_generate_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root")
    parser.add_argument("--out")
    parser.add_argument("--format", choices=["json", "md", "dot"], default="json")
    parser.add_argument("--detail", "--map-detail", dest="detail",
                        choices=["files", "symbols", "full"], default="full")
    parser.add_argument("--max-files", "--map-max-files", dest="max_files",
                        type=int, default=4000)
    parser.add_argument("--max-kb", "--map-max-kb", dest="max_kb", type=int, default=512)
    parser.add_argument("--max-symbols", type=int, default=200)
    parser.add_argument("--budget-ms", "--map-budget-ms", dest="budget_ms",
                        type=int, default=30_000)
    parser.add_argument("--langs", "--map-langs", dest="langs",
                        help="comma-separated language names")
    parser.add_argument("--kind", action="append", help="symbol or type kind")
    parser.add_argument("--role", action="append", help="file role")
    parser.add_argument("--path", action="append", help="path glob")
    parser.add_argument("--target", action="append", help="target platform")
    parser.add_argument("--map-target", help="comma-separated target classes")
    parser.add_argument("--exported-only", action="store_true")
    parser.add_argument("--min-role-confidence", type=float, default=0.0)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="sourcemap",
                                     description="Map symbols, imports and roles in a source tree.")
    sub = parser.add_subparsers(dest="command")
    generate = sub.add_parser("generate", help="generate a repo map")
    _add_generate_flags(generate)
    _add_generate_flags(parser)
    parser.set_defaults(command="generate")
    query = sub.add_parser("query", help="query an existing map artifact")
    query.add_argument("--map", required=True)
    query.add_argument("--kind")
    query.add_argument("--role")
    query.add_argument("--lang", dest="langs")
    query.add_argument("--path")
    query.add_argument("--target")
    query.add_argument("--exported-only", action="store_true")
    query.add_argument("--min-role-confidence", type=float, default=0.0)
    query.set_defaults(command="query")
    args = parser.parse_args(argv)
    spec = _filter(args)

    if args.command == "query":
        bundle = json.loads(Path(args.map).read_text(encoding="utf-8"))
        filtered = RepoMap.filter_map(bundle, spec)
        info = filtered.get("filter", {})
        payload = {
            "matched_files": info.get("matched_files", len(filtered.get("files", {}))),
            "matched_symbols": info.get("matched_symbols", 0),
            "applied": info.get("applied", False),
            "files": sorted(filtered.get("files", {})),
        }
        if spec.kinds:
            has_symbols = any(entry.get("symbols")
                              for entry in bundle.get("files", {}).values())
            if not has_symbols:
                payload["hint"] = "symbol detail is required: regenerate with --map-detail full"
        print(json.dumps(payload, sort_keys=True))
        return 0

    if not args.root or not args.out:
        parser.error("generate mode needs --root and --out")
    if spec.kinds and args.detail == "files":
        print("kinds need symbols; use --map-detail full instead", file=sys.stderr)
        return 2
    mapper = RepoMap(max_files=args.max_files, max_kb=args.max_kb,
                     max_symbols=args.max_symbols, detail=args.detail,
                     langs=list(_csv(args.langs)), filter=spec,
                     target_classes=list(spec.targets) or None,
                     budget_ms=args.budget_ms)
    bundle = mapper.generate(Path(args.root))
    write(Path(args.out), bundle, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

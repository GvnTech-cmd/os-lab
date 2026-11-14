"""Export JSON Schema and TypeScript from the engine's Python data models.

The small validator supports the schema vocabulary emitted by this module. It
is deliberately not a general-purpose implementation of all of JSON Schema.
"""
from __future__ import annotations

import argparse
import dataclasses
from enum import Enum
import json
import math
from pathlib import Path
import types
from typing import Any, Union, get_args, get_origin, get_type_hints

from source_lab.evidence import schema as evidence
from source_lab.sourcemap import model as maps
from source_lab.sourcemap.targets import Target

MODELS = (evidence.EvidenceSpan, evidence.FindingScope, evidence.TargetIdentity,
          evidence.Finding, evidence.Coverage, maps.ReturnShape, maps.Param,
          maps.Symbol, maps.ImportRef, maps.Role, maps.FileMap, Target)


def _type(annotation: Any) -> dict:
    origin, args = get_origin(annotation), get_args(annotation)
    if annotation is Any:
        return {}
    if annotation is type(None):
        return {"type": "null"}
    if origin in (Union, types.UnionType):
        return {"anyOf": [_type(item) for item in args]}
    if origin is list:
        return {"type": "array", "items": _type(args[0])}
    if origin is dict:
        return {"type": "object", "additionalProperties": _type(args[1])}
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return {"type": "string", "enum": [item.value for item in annotation]}
    if dataclasses.is_dataclass(annotation):
        return {"$ref": f"#/$defs/{annotation.__name__}"}
    return {"type": {str: "string", int: "integer", float: "number", bool: "boolean"}[annotation]}


def _object(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required}


def schema_document() -> dict:
    definitions = {}
    for model in MODELS:
        hints = get_type_hints(model)
        properties, required = {}, []
        for field in dataclasses.fields(model):
            if model is maps.FileMap and field.name == "path":
                continue  # File paths are dictionary keys in the serialized map.
            value = _type(hints[field.name])
            if field.name == "schema_version":
                value = {"type": "integer", "const": 2}
            if field.name == "confidence":
                value.update(minimum=0, maximum=1)
            properties[field.name] = value
            if field.default is not None and not (model is maps.Symbol and field.name == "meta"):
                required.append(field.name)
        definitions[model.__name__] = _object(properties, required)
    definitions["Finding"]["properties"]["phase"] = {"enum": ["static", "dynamic", "correlation"]}
    definitions["Finding"]["properties"]["evidence"]["minItems"] = 1
    definitions["Finding"]["properties"]["finding_id"]["minLength"] = 1
    definitions["Finding"]["properties"]["hypothesis"]["minLength"] = 1
    definitions["TargetIdentity"]["properties"]["identifier"]["minLength"] = 1
    definitions["Finding"]["properties"]["rule_id"] = {"type": "string"}
    definitions["Finding"]["required"].append("rule_id")
    for name in ("scanned_files", "skipped_files"):
        definitions["Coverage"]["properties"][name]["minimum"] = 0
    # These envelopes are produced directly as dictionaries by the engine. Their
    # schema lives here; frontend contracts are generated, never maintained by hand.
    definitions["AnalysisV2"] = _object({
        "schema_version": {"type": "integer", "const": 2},
        "target": {"$ref": "#/$defs/TargetIdentity"},
        "coverage": {"$ref": "#/$defs/Coverage"},
        "findings": {"type": "array", "items": {"$ref": "#/$defs/Finding"}},
        "scorecard": {"type": "object"},
    }, ["schema_version", "target", "coverage", "findings"])
    definitions["RepoMapV1"] = _object({
        "schema_version": {"type": "integer", "const": 1}, "root": {"type": "string"},
        "toolchain": {"type": "object"}, "stats": {"type": "object"},
        "files": {"type": "object", "additionalProperties": {"$ref": "#/$defs/FileMap"}},
        "targets": {"type": "array", "items": {"$ref": "#/$defs/Target"}},
        "coverage": _object({"files_scanned": {"type": "integer", "minimum": 0},
                             "files_parsed": {"type": "integer", "minimum": 0},
                             "applicability": {"enum": ["full", "partial", "not_applicable"]},
                             "limitations": {"type": "array", "items": {"type": "string"}}}),
        "types": {"type": "object"}, "entrypoints": {"type": "array"},
        "cycles": {"type": "array"}, "filter": {"type": "object"},
        "tree": {"type": "array"}, "edges": {"type": "array"}, "externals": {"type": "object"},
    })
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": definitions}


def validate(value: Any, kind: str) -> list[str]:
    """Return payload errors without evaluating input as code or accepting new versions."""
    document = schema_document()
    if kind not in document["$defs"]:
        return [f"Unknown contract: {kind}"]

    def check(value, spec, path):
        if "$ref" in spec:
            return check(value, document["$defs"][spec["$ref"].rsplit("/", 1)[-1]], path)
        if "anyOf" in spec:
            return [] if any(not check(value, option, path) for option in spec["anyOf"]) else [f"{path}: invalid value type"]
        errors = []
        expected = spec.get("type")
        matches = {"string": isinstance(value, str), "integer": type(value) is int,
                   "number": type(value) in (int, float), "boolean": type(value) is bool,
                   "null": value is None, "object": isinstance(value, dict), "array": isinstance(value, list)}
        if expected and not matches[expected]:
            return [f"{path}: expected {expected}"]
        if expected == "number" and type(value) is float and not math.isfinite(value):
            return [f"{path}: non-finite number"]
        if "const" in spec and (type(value) is not int or value != spec["const"]):
            errors.append(f"{path}: unsupported version (expected {spec['const']})")
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"{path}: invalid enum value")
        for limit in ("minimum", "maximum"):
            if limit in spec and ((limit == "minimum" and value < spec[limit]) or (limit == "maximum" and value > spec[limit])):
                errors.append(f"{path}: violates {limit}")
        if "minLength" in spec and len(value) < spec["minLength"]:
            errors.append(f"{path}: empty string")
        if isinstance(value, dict):
            properties = spec.get("properties", {})
            errors += [f"{path}.{name}: required" for name in spec.get("required", []) if name not in value]
            for name, item in value.items():
                child = properties.get(name, spec.get("additionalProperties", {}))
                if isinstance(child, dict):
                    errors += check(item, child, f"{path}.{name}")
        if isinstance(value, list):
            if len(value) < spec.get("minItems", 0):
                errors.append(f"{path}: too few items")
            for index, item in enumerate(value):
                errors += check(item, spec.get("items", {}), f"{path}[{index}]")
        return errors
    return check(value, document["$defs"][kind], kind)


def _ts(spec: dict) -> str:
    if "$ref" in spec:
        return spec["$ref"].rsplit("/", 1)[-1]
    if "const" in spec:
        return json.dumps(spec["const"])
    if "enum" in spec:
        return " | ".join(json.dumps(value) for value in spec["enum"])
    if "anyOf" in spec:
        return " | ".join(_ts(item) for item in spec["anyOf"])
    kind = spec.get("type")
    if kind == "array":
        return f"Array<{_ts(spec.get('items', {}))}>"
    if kind == "object":
        if "properties" not in spec:
            return f"Record<string, {_ts(spec.get('additionalProperties', {}))}>"
        fields = [f"{json.dumps(name)}{'' if name in spec.get('required', []) else '?'}: {_ts(value)}"
                  for name, value in spec["properties"].items()]
        return "{ " + "; ".join(fields) + " }"
    return {"string": "string", "integer": "number", "number": "number",
            "boolean": "boolean", "null": "null"}.get(kind, "unknown")


def typescript() -> str:
    return "// Generated by Source Lab contracts; do not edit.\n" + "\n".join(
        f"export type {name} = {_ts(spec)};" for name, spec in schema_document()["$defs"].items()) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json", "typescript"), default="json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", type=Path, help="Validate a local JSON artifact")
    parser.add_argument("--kind", default="AnalysisV2")
    args = parser.parse_args(argv)
    if args.check:
        errors = validate(json.loads(args.check.read_text()), args.kind)
        print(json.dumps({"valid": not errors, "errors": errors}))
        return int(bool(errors))
    content = typescript() if args.format == "typescript" else json.dumps(schema_document(), indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(content)
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

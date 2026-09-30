#!/usr/bin/env python3
"""Generate ``src/meterflow/types.py`` from the frozen OpenAPI contract (``docs/openapi.json``).

The Python counterpart of the Node SDK's ``openapi-typescript`` step: types only, no runtime code.
Only the schemas reachable from the SDK-facing operations (credits, usage, subscriptions, plans
reads, entitlements) are emitted, so the JWT/dashboard surface never leaks into the package.

    python scripts/generate_types.py            # rewrite types.py
    python scripts/generate_types.py --check    # exit 1 if types.py is stale (CI)

Standard library only — nothing to install. Objects become ``TypedDict``s (a required-keys base plus
a ``total=False`` subclass when the schema has optional keys, which keeps the 3.10 floor without
``NotRequired``), string enums become ``Literal`` aliases, ``anyOf … null`` becomes ``X | None``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OPENAPI_PATH = HERE.parent.parent.parent / "docs" / "openapi.json"
OUTPUT_PATH = HERE.parent / "src" / "meterflow" / "types.py"

# (path prefix, allowed methods) — the public SDK surface, matching the Node SDK resource files.
SDK_OPERATIONS: dict[str, set[str]] = {
    "/api/v1/credits": {"get", "post"},
    "/api/v1/usage": {"get", "post"},
    "/api/v1/subscriptions": {"get", "post", "patch", "delete"},
    "/api/v1/plans": {"get"},
    "/api/v1/entitlements": {"get"},
}

REF_PREFIX = "#/components/schemas/"


def schema_name(ref: str) -> str:
    return ref.removeprefix(REF_PREFIX)


def collect_refs(node: Any, found: set[str]) -> None:
    """Every ``$ref`` under ``node`` — walked recursively, dicts and lists alike."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            found.add(schema_name(ref))
        for value in node.values():
            collect_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_refs(item, found)


def sdk_schema_names(spec: dict[str, Any]) -> list[str]:
    """Schemas used by the SDK operations' request bodies and 2xx responses, plus everything they reference."""
    seeds: set[str] = set()
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            allowed = next((methods for prefix, methods in SDK_OPERATIONS.items() if path.startswith(prefix)), None)
            if allowed is None or method not in allowed:
                continue
            collect_refs(operation.get("requestBody"), seeds)
            for status, response in operation.get("responses", {}).items():
                if status.startswith("2"):
                    collect_refs(response, seeds)

    schemas = spec["components"]["schemas"]
    closure: set[str] = set()
    pending = list(seeds)
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        closure.add(name)
        nested: set[str] = set()
        collect_refs(schemas[name], nested)
        pending.extend(nested - closure)
    return sorted(closure)


def python_type(schema: dict[str, Any]) -> str:
    """The annotation for one schema node."""
    if "$ref" in schema:
        return schema_name(schema["$ref"])
    if "anyOf" in schema:
        options = [python_type(option) for option in schema["anyOf"]]
        # `X | None` reads better with None last, whatever order the spec used.
        ordered = [option for option in options if option != "None"] + [option for option in options if option == "None"]
        return " | ".join(dict.fromkeys(ordered))
    if "enum" in schema:
        return "Literal[" + ", ".join(json.dumps(value) for value in schema["enum"]) + "]"
    kind = schema.get("type")
    if kind == "string":
        return "str"
    if kind == "integer":
        return "int"
    if kind == "number":
        return "float"
    if kind == "boolean":
        return "bool"
    if kind == "null":
        return "None"
    if kind == "array":
        return f"list[{python_type(schema.get('items', {}))}]"
    if kind == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict) and extra:
            return f"dict[str, {python_type(extra)}]"
        return "dict[str, Any]"
    return "Any"


def docstring(schema: dict[str, Any], indent: str) -> list[str]:
    description = schema.get("description")
    if not description:
        return []
    text = " ".join(str(description).split())
    return [f'{indent}"""{text}"""', ""]


def render_enum(name: str, schema: dict[str, Any]) -> list[str]:
    values = ", ".join(json.dumps(value) for value in schema["enum"])
    return [f"{name} = Literal[{values}]", ""]


def render_object(name: str, schema: dict[str, Any]) -> list[str]:
    properties: dict[str, Any] = schema.get("properties", {})
    if not properties:
        return [f"{name} = dict[str, Any]", ""]
    required = [key for key in properties if key in set(schema.get("required", []))]
    optional = [key for key in properties if key not in required]
    lines: list[str] = []

    def fields(keys: list[str]) -> list[str]:
        return [f"    {key}: {python_type(properties[key])}" for key in keys]

    if required and optional:
        base = f"_{name}Required"
        lines += [f"class {base}(TypedDict):", *fields(required), "", ""]
        lines += [f"class {name}({base}, total=False):", *docstring(schema, "    "), *fields(optional), "", ""]
    elif required:
        lines += [f"class {name}(TypedDict):", *docstring(schema, "    "), *fields(required), "", ""]
    else:
        lines += [f"class {name}(TypedDict, total=False):", *docstring(schema, "    "), *fields(optional), "", ""]
    return lines


def render(spec: dict[str, Any]) -> str:
    schemas = spec["components"]["schemas"]
    names = sdk_schema_names(spec)
    enums = [name for name in names if "enum" in schemas[name]]
    objects = [name for name in names if "enum" not in schemas[name]]

    out: list[str] = [
        "# GENERATED by scripts/generate_types.py from docs/openapi.json — DO NOT EDIT.",
        f"# OpenAPI version: {spec['info']['version']}. Re-run the script after the contract changes; CI fails on drift.",
        '"""Request and response shapes of the SDK-facing API, as TypedDicts (plain dicts at runtime)."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any, Literal, TypedDict",
        "",
    ]
    for name in enums:
        out += render_enum(name, schemas[name])
    if enums:
        out.append("")
    for name in objects:
        out += render_object(name, schemas[name])
    out += ["__all__ = [", *[f'    "{name}",' for name in names], "]", ""]
    text = "\n".join(out)
    return re.sub(r"\n{4,}", "\n\n\n", text)


def main(argv: list[str]) -> int:
    spec = json.loads(OPENAPI_PATH.read_text())
    generated = render(spec)
    if "--check" in argv:
        current = OUTPUT_PATH.read_text() if OUTPUT_PATH.exists() else ""
        if current != generated:
            print(f"{OUTPUT_PATH.relative_to(HERE.parent)} is stale — run scripts/generate_types.py", file=sys.stderr)
            return 1
        print("types.py is up to date")
        return 0
    OUTPUT_PATH.write_text(generated)
    print(f"wrote {OUTPUT_PATH.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

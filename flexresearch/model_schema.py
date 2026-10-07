"""Portable function parameters for providers that wrap a schema before use.

Pydantic local refs are valid relative to the parameter schema root. Some
providers embed that schema in an array and then resolve refs against the
wrong root. Inline finite local refs at the transport boundary, without
relaxing the Pydantic models used to validate real tool arguments.
"""

from copy import deepcopy
from typing import Any


def inline_local_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Expand local JSON Pointers; reject external/cyclic refs without I/O.

    Walk schema positions only: defaults/examples and property names are data,
    so a literal ``$ref`` or ``$defs`` there must remain untouched. Ref siblings
    are conjoined with allOf rather than overwriting referenced constraints.
    """
    schema_maps = {"properties", "patternProperties", "dependentSchemas"}
    schema_lists = {"allOf", "anyOf", "oneOf", "prefixItems"}
    schema_values = {"additionalProperties", "unevaluatedProperties", "propertyNames", "items", "contains", "additionalItems", "unevaluatedItems", "not", "if", "then", "else"}

    def resolve(reference: str) -> Any:
        if not reference.startswith("#/"):
            raise ValueError("tool schema requires a finite local JSON Pointer")
        target: Any = schema
        try:
            for part in reference[2:].split("/"):
                key = part.replace("~1", "/").replace("~0", "~")
                target = target[int(key)] if isinstance(target, list) else target[key]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError("tool schema contains an unresolved local reference") from exc
        if not isinstance(target, (dict, bool)):
            raise ValueError("tool schema reference must resolve to a schema")
        return target

    def visit(node: Any, stack: tuple[str, ...] = ()) -> Any:
        if isinstance(node, bool):
            return node
        if not isinstance(node, dict):
            raise ValueError("invalid tool parameter schema")
        if "$ref" in node:
            reference = node["$ref"]
            if not isinstance(reference, str) or reference in stack:
                raise ValueError("recursive tool parameter schemas are not supported")
            expanded = visit(resolve(reference), (*stack, reference))
            siblings = {key: value for key, value in node.items() if key not in {"$ref", "$defs", "definitions"}}
            return {"allOf": [expanded, visit(siblings, stack)]} if siblings else expanded
        result = {}
        for key, value in node.items():
            if key in {"$defs", "definitions"}:
                continue
            if key in schema_maps:
                result[key] = {name: visit(child, stack) for name, child in value.items()}
            elif key in schema_lists:
                result[key] = [visit(child, stack) for child in value]
            elif key in schema_values:
                result[key] = [visit(child, stack) for child in value] if isinstance(value, list) else visit(value, stack)
            else:
                result[key] = deepcopy(value)
        return result

    return visit(schema)


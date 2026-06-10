"""
peft/_yaml.py — Minimal inline YAML serializer

A stdlib-only YAML writer for dicts/lists/scalars.
Used by compiler, registry, and deployment to write .yaml files
without taking a PyYAML dependency.
"""
from __future__ import annotations


def dict_to_yaml(d: object, indent: int = 0) -> str:
    """Recursively serialize a Python object to YAML text.

    Handles: dict, list, str, int, float, bool, None.
    All other types are coerced to str.
    """
    pad = "  " * indent
    lines: list[str] = []

    if isinstance(d, dict):
        for k, v in d.items():
            key_str = f"{pad}{k}:"
            if isinstance(v, dict) and v:
                lines.append(key_str)
                lines.append(dict_to_yaml(v, indent + 1))
            elif isinstance(v, list) and v:
                lines.append(key_str)
                for item in v:
                    if isinstance(item, dict):
                        # First key of the dict gets the dash
                        sub = dict_to_yaml(item, indent + 2)
                        sub_lines = sub.splitlines()
                        if sub_lines:
                            lines.append(f"{pad}  - {sub_lines[0].lstrip()}")
                            for sl in sub_lines[1:]:
                                lines.append(f"{pad}    {sl.lstrip()}")
                    else:
                        lines.append(f"{pad}  - {_scalar(item)}")
            else:
                lines.append(f"{key_str} {_scalar(v)}")
    elif isinstance(d, list):
        for item in d:
            if isinstance(item, dict):
                sub = dict_to_yaml(item, indent + 1)
                sub_lines = sub.splitlines()
                if sub_lines:
                    lines.append(f"{pad}- {sub_lines[0].lstrip()}")
                    for sl in sub_lines[1:]:
                        lines.append(f"{pad}  {sl.lstrip()}")
            else:
                lines.append(f"{pad}- {_scalar(item)}")
    else:
        lines.append(f"{pad}{_scalar(d)}")

    return "\n".join(lines)


def _scalar(v: object) -> str:
    """Format a scalar value for YAML output."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # Quote strings containing YAML special characters
    # Note: hyphen (-) is intentionally excluded from the special-char set so
    # that kebab-case identifiers like "kjv-tokenless-v1" are not needlessly quoted.
    if any(c in s for c in (":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", "<", ">", "=", "!", "%", "@", "`")):
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s

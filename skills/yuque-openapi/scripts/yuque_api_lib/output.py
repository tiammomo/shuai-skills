from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from .client import unwrap_data
from .core import YuqueApiError

def parse_select_fields(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]

def extract_field(value: Any, field_path: str) -> Any:
    current = value
    for segment in field_path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if 0 <= index < len(current):
                current = current[index]
            else:
                return None
        else:
            return None
    return current

def project_data(value: Any, fields: List[str]) -> Any:
    if not fields:
        return value
    if isinstance(value, list):
        return [project_item(item, fields) for item in value]
    return project_item(value, fields)

def project_item(value: Any, fields: List[str]) -> Any:
    if len(fields) == 1:
        return extract_field(value, fields[0])
    return {field: extract_field(value, field) for field in fields}

def normalize_rows(value: Any) -> Tuple[List[str], List[Dict[str, Any]]]:
    if isinstance(value, list):
        if not value:
            return [], []
        if all(isinstance(item, dict) for item in value):
            return list(value[0].keys()), [dict(item) for item in value]
        return ["value"], [{"value": item} for item in value]
    if isinstance(value, dict):
        return list(value.keys()), [dict(value)]
    return ["value"], [{"value": value}]

def stringify_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

def emit_jsonl(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
        return
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))

def emit_table(value: Any) -> None:
    headers, rows = normalize_rows(value)
    if not headers and not rows:
        return
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(stringify_cell(row.get(header))))
    print("  ".join(header.ljust(widths[header]) for header in headers))
    print("  ".join("-" * widths[header] for header in headers))
    for row in rows:
        print("  ".join(stringify_cell(row.get(header)).ljust(widths[header]) for header in headers))

def render_text_line(value: Any) -> str:
    if isinstance(value, dict):
        return "\t".join(stringify_cell(v) for v in value.values())
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return stringify_cell(value)

def emit_text(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            print(render_text_line(item))
        return
    print(render_text_line(value))

def emit_result(result: Any, *, output: str, select: Optional[str]) -> None:
    fields = parse_select_fields(select)
    if output == "json" and not fields:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return

    projected = project_data(unwrap_data(result), fields)
    if output == "json":
        print(json.dumps(projected, ensure_ascii=False, indent=2, sort_keys=True))
    elif output == "jsonl":
        emit_jsonl(projected)
    elif output == "table":
        emit_table(projected)
    elif output == "text":
        emit_text(projected)

def emit_error(exc: YuqueApiError) -> int:
    payload = exc.payload
    message = {"error": str(exc)}
    if exc.status is not None:
        message["status"] = exc.status
    if exc.method:
        message["method"] = exc.method
    if exc.path:
        message["path"] = exc.path
    if payload is not None:
        message["payload"] = payload
    print(json.dumps(message, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    return 1

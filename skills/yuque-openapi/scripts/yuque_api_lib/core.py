from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_BASE_URL = "https://www.yuque.com/api/v2"
DEFAULT_TIMEOUT = 30
DEFAULT_LIMIT = 100
DEFAULT_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.0
DEFAULT_RETRY_MAX_BACKOFF = 8.0
DEFAULT_INDEX_FILE = "yuque-index.json"
SNAPSHOT_SCHEMA_VERSION = 1


class YuqueApiError(RuntimeError):
    """Raised when the Yuque API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        payload: Any = None,
        method: Optional[str] = None,
        path: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload
        self.method = method
        self.path = path


def maybe_json(raw: Any, *, field_name: str) -> Dict[str, Any]:
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise YuqueApiError(f"{field_name} must be valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise YuqueApiError(f"{field_name} must decode to a JSON object.")
        return value
    raise YuqueApiError(f"{field_name} must be a JSON object or JSON string.")

def read_body(body: Optional[str], body_file: Optional[str]) -> Optional[str]:
    if body is not None and body_file is not None:
        raise YuqueApiError("Use either --body or --body-file, not both.")
    if body is not None:
        return body
    if body_file is None:
        return None
    if body_file == "-":
        return sys.stdin.read()
    return Path(body_file).read_text(encoding="utf-8")

def choose_body_field(fmt: str, explicit_field: str) -> str:
    if explicit_field != "auto":
        return explicit_field
    if fmt in {"lake", "asl"}:
        return "body_asl"
    return "body"


def emit_progress(message: str) -> None:
    print(message, file=sys.stderr)

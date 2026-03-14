from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .core import YuqueApiError
from .dir_sync_types import IndexEntry, RecordLike, RecordMaps, SyncPlanItem
from .dir_sync_utils import normalize_relative_path
from .markdown_docs import current_utc_timestamp


def load_index_document(index_path: Path) -> Dict[str, Any]:
    if not index_path.exists():
        return {}
    try:
        raw = index_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise YuqueApiError(f"Unable to read index file {index_path}: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise YuqueApiError(f"Index file must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise YuqueApiError("Index file must be a JSON object.")
    return parsed


def index_entries_from_document(document: Dict[str, Any], root_dir: Path) -> List[IndexEntry]:
    raw_entries = document.get("docs") or document.get("files") or []
    if not isinstance(raw_entries, list):
        raise YuqueApiError("Index file docs/files field must be a JSON array.")

    entries: List[IndexEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        entry: IndexEntry = dict(raw_entry)
        relative_path = normalize_relative_path(entry.get("relative_path") or entry.get("path"), root_dir)
        if relative_path:
            entry["relative_path"] = relative_path
        if entry.get("doc_id") is None and entry.get("id") is not None:
            entry["doc_id"] = str(entry["id"])
        elif entry.get("doc_id") is not None:
            entry["doc_id"] = str(entry["doc_id"])
        if entry.get("doc_slug") is None and entry.get("slug") is not None:
            entry["doc_slug"] = str(entry["slug"])
        elif entry.get("doc_slug") is not None:
            entry["doc_slug"] = str(entry["doc_slug"])
        entries.append(entry)
    return entries


def build_record_maps(records: Sequence[RecordLike]) -> RecordMaps:
    maps: RecordMaps = {
        "by_doc_id": {},
        "by_doc_slug": {},
        "by_relative_path": {},
    }
    for record in records:
        relative_path = record.get("relative_path")
        if relative_path:
            maps["by_relative_path"][str(relative_path)] = record
        doc_id = record.get("doc_id")
        if doc_id not in (None, ""):
            maps["by_doc_id"][str(doc_id)] = record
        doc_slug = record.get("doc_slug")
        if doc_slug not in (None, ""):
            maps["by_doc_slug"][str(doc_slug)] = record
    return maps


def build_sync_index_entry(
    item: SyncPlanItem,
    *,
    result_data: Dict[str, Any] | None = None,
) -> IndexEntry:
    local = item.get("_local")
    remote = item.get("_remote")
    base_entry = item.get("_base_entry") or {}

    doc_id = (result_data or {}).get("doc_id") or item.get("doc_id") or base_entry.get("doc_id")
    doc_slug = (result_data or {}).get("doc_slug") or item.get("doc_slug") or base_entry.get("doc_slug")
    title = (result_data or {}).get("title") or item.get("title") or base_entry.get("title")

    content_hash = item.get("remote_hash") or item.get("local_hash") or base_entry.get("content_hash")
    if local and item.get("status") in {"push", "skip"}:
        content_hash = local.get("content_hash") or content_hash
    if remote and item.get("status") in {"pull", "skip"}:
        content_hash = remote.get("content_hash") or content_hash

    public_value = (remote.get("public") if remote else None) if remote is not None else (local.get("public") if local else None)
    if public_value is None:
        public_value = base_entry.get("public")

    format_value = remote.get("format") if remote else "markdown"
    if format_value in (None, ""):
        format_value = base_entry.get("format") or "markdown"

    return {
        "relative_path": item.get("relative_path"),
        "doc_id": str(doc_id) if doc_id not in (None, "") else None,
        "doc_slug": str(doc_slug) if doc_slug not in (None, "") else None,
        "title": str(title or Path(str(item.get("relative_path") or "doc.md")).stem),
        "public": public_value,
        "format": format_value,
        "updated_at": (remote.get("updated_at") if remote else None) or base_entry.get("updated_at"),
        "content_hash": content_hash,
        "last_sync_at": current_utc_timestamp(),
    }


def index_entry_key(entry: IndexEntry) -> str:
    if entry.get("doc_id") not in (None, ""):
        return f"id:{entry['doc_id']}"
    return f"path:{entry.get('relative_path') or ''}"


def merge_index_entries(existing_entries: Sequence[IndexEntry], updated_entries: Sequence[IndexEntry]) -> List[IndexEntry]:
    merged: Dict[str, IndexEntry] = {}
    for entry in existing_entries:
        merged[index_entry_key(entry)] = dict(entry)
    for entry in updated_entries:
        merged[index_entry_key(entry)] = dict(entry)
    return sorted(
        merged.values(),
        key=lambda entry: (
            str(entry.get("relative_path") or ""),
            str(entry.get("doc_id") or ""),
        ),
    )


def write_sync_index(index_path: Path, repo_ref: str, entries: Sequence[IndexEntry]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(
            {
                "repo": repo_ref,
                "generated_at": current_utc_timestamp(),
                "count": len(entries),
                "docs": list(entries),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

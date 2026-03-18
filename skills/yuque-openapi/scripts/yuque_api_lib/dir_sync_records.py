from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .client import YuqueClient, fetch_doc_detail, fetch_repo_doc_summaries, fetch_repo_toc
from .core import DEFAULT_LIMIT, YuqueApiError
from .dir_sync_types import IndexEntry, LocalMarkdownRecord, RecordLike, RecordMaps, RemoteMarkdownRecord
from .dir_sync_utils import build_toc_path_map, choose_remote_relative_path, find_record
from .markdown_docs import (
    coerce_public_flag,
    derive_markdown_title,
    doc_markdown_body,
    front_matter_text,
    hash_markdown_content,
    split_front_matter,
)


def load_local_markdown_records(root_dir: Path) -> List[LocalMarkdownRecord]:
    if not root_dir.exists():
        return []
    records: List[LocalMarkdownRecord] = []
    for path in sorted(root_dir.rglob("*.md")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root_dir)
        raw_markdown = path.read_text(encoding="utf-8")
        front_matter, body = split_front_matter(raw_markdown)
        records.append(
            {
                "absolute_path": str(path.resolve()),
                "relative_path": relative_path.as_posix(),
                "front_matter": front_matter,
                "raw_markdown": raw_markdown,
                "body": body,
                "content_hash": hash_markdown_content(body),
                "title": derive_markdown_title(body, front_matter_text(front_matter, "title") or path.stem),
                "public": coerce_public_flag(front_matter.get("public")),
                "doc_id": front_matter_text(front_matter, "yuque_doc_id"),
                "doc_slug": front_matter_text(front_matter, "yuque_doc_slug"),
                "updated_at": front_matter_text(front_matter, "updated_at"),
            }
        )
    return records


def fetch_remote_markdown_records(
    client: YuqueClient,
    repo_ref: str,
    *,
    index_maps: RecordMaps,
    local_maps: RecordMaps,
    name_by: str,
    flat: bool,
) -> List[RemoteMarkdownRecord]:
    docs = fetch_repo_doc_summaries(client, repo_ref)
    if not isinstance(docs, list):
        raise YuqueApiError("Expected doc list while building directory sync state.")

    toc_path_map = {} if flat else build_toc_path_map(fetch_repo_toc(client, repo_ref), name_by)

    records: List[RemoteMarkdownRecord] = []
    for item in docs:
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("id") or "")
        if not doc_id:
            continue
        records.append(
            {
                "doc_id": doc_id,
                "doc_slug": str(item.get("slug") or ""),
                "title": str(item.get("title") or ""),
                "public": item.get("public"),
                "format": item.get("format"),
                "updated_at": item.get("updated_at"),
                "body": "",
                "content_hash": None,
                "relative_path": choose_remote_relative_path(
                    item,
                    index_maps=index_maps,
                    local_maps=local_maps,
                    toc_path_map=toc_path_map,
                    name_by=name_by,
                ),
            }
        )
    records.sort(key=lambda record: (record.get("relative_path") or "", record.get("doc_id") or ""))
    return records


def ensure_remote_markdown_record_detail(
    client: YuqueClient,
    repo_ref: str,
    remote_record: RemoteMarkdownRecord,
) -> Tuple[RemoteMarkdownRecord, bool]:
    if remote_record.get("content_hash") not in (None, "") and remote_record.get("body") is not None:
        return remote_record, False

    doc_id = str(remote_record.get("doc_id") or "")
    if not doc_id:
        raise YuqueApiError("Remote directory sync record is missing doc_id, so detail hydration cannot continue.")

    doc = fetch_doc_detail(client, repo_ref, doc_id)
    body = doc_markdown_body(doc)
    remote_record["doc_slug"] = str(doc.get("slug") or remote_record.get("doc_slug") or "")
    remote_record["title"] = str(doc.get("title") or remote_record.get("title") or "")
    remote_record["public"] = doc.get("public", remote_record.get("public"))
    remote_record["format"] = doc.get("format", remote_record.get("format"))
    remote_record["updated_at"] = doc.get("updated_at", remote_record.get("updated_at"))
    remote_record["body"] = body
    remote_record["content_hash"] = hash_markdown_content(body)
    return remote_record, True


def find_base_entry(
    index_maps: RecordMaps,
    *,
    local: Optional[RecordLike],
    remote: Optional[RecordLike],
) -> Optional[IndexEntry]:
    entry = (
        find_record(
            index_maps["by_relative_path"],
            local.get("relative_path") if local else None,
            remote.get("relative_path") if remote else None,
        )
        or find_record(
            index_maps["by_doc_id"],
            local.get("doc_id") if local else None,
            remote.get("doc_id") if remote else None,
        )
        or find_record(
            index_maps["by_doc_slug"],
            local.get("doc_slug") if local else None,
            remote.get("doc_slug") if remote else None,
        )
    )
    if entry is None:
        return None
    return dict(entry)

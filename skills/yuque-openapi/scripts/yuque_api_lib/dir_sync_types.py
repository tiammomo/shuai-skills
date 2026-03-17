from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, TypeAlias, TypedDict


class IndexEntry(TypedDict, total=False):
    relative_path: str
    doc_id: Optional[str]
    doc_slug: Optional[str]
    title: str
    public: Any
    format: Optional[str]
    updated_at: Optional[str]
    content_hash: Optional[str]
    last_sync_at: str


class LocalMarkdownRecord(TypedDict, total=False):
    absolute_path: str
    relative_path: str
    front_matter: Dict[str, Any]
    raw_markdown: str
    body: str
    content_hash: str
    title: str
    public: Optional[int]
    doc_id: Optional[str]
    doc_slug: Optional[str]
    updated_at: Optional[str]


class RemoteMarkdownRecord(TypedDict, total=False):
    doc_id: str
    doc_slug: str
    title: str
    public: Any
    format: Optional[str]
    updated_at: Optional[str]
    body: str
    content_hash: str
    relative_path: str


RecordLike: TypeAlias = IndexEntry | LocalMarkdownRecord | RemoteMarkdownRecord


class RecordMaps(TypedDict):
    by_doc_id: Dict[str, RecordLike]
    by_doc_slug: Dict[str, RecordLike]
    by_relative_path: Dict[str, RecordLike]


class SyncPlanItem(TypedDict, total=False):
    status: str
    reason: str
    relative_path: str
    local_path: str
    doc_id: Optional[str]
    doc_slug: Optional[str]
    title: str
    local_hash: Optional[str]
    remote_hash: Optional[str]
    base_hash: Optional[str]
    remote_updated_at: Optional[str]
    review: Dict[str, Any]
    diff_preview: Dict[str, Any]
    operation: Optional[Dict[str, Any]]
    _local: Optional[LocalMarkdownRecord]
    _remote: Optional[RemoteMarkdownRecord]
    _base_entry: Optional[IndexEntry]


class DirSyncPlan(TypedDict):
    data: List[Dict[str, Any]]
    meta: Dict[str, Any]
    operations: List[Dict[str, Any]]


class DirSyncState(TypedDict):
    root_dir: Path
    index_path: Path
    existing_entries: List[IndexEntry]
    items: List[SyncPlanItem]

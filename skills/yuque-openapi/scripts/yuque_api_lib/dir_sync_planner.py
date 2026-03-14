from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .client import YuqueClient
from .dir_sync_records import fetch_remote_markdown_records, find_base_entry, load_local_markdown_records
from .dir_sync_store import build_record_maps, index_entries_from_document, load_index_document
from .dir_sync_types import DirSyncPlan, DirSyncState, IndexEntry, LocalMarkdownRecord, RemoteMarkdownRecord, SyncPlanItem
from .dir_sync_utils import derive_dir_sync_slug, find_record, flat_relative_markdown_path, reserve_unique_slug


def build_push_operation(
    *,
    repo_ref: str,
    local: LocalMarkdownRecord,
    remote: Optional[RemoteMarkdownRecord],
    base_entry: Optional[IndexEntry],
    slug_source: str,
    reserved_slugs: Set[str],
    default_public: Optional[int],
    lookup_by: str,
) -> Dict[str, Any]:
    operation: Dict[str, Any] = {
        "command": "push-markdown",
        "repo": repo_ref,
        "source": local["absolute_path"],
    }
    if remote and remote.get("doc_id"):
        operation["doc"] = str(remote["doc_id"])
        operation["lookup_by"] = "id"
    else:
        lookup_doc = local.get("doc_id") or (base_entry.get("doc_id") if base_entry else None) or local.get("doc_slug") or (base_entry.get("doc_slug") if base_entry else None)
        if lookup_doc not in (None, ""):
            operation["doc"] = str(lookup_doc)
            if lookup_by == "auto":
                operation["lookup_by"] = "id" if str(lookup_doc).isdigit() else "slug"
            else:
                operation["lookup_by"] = lookup_by

        slug_value = local.get("doc_slug") or (base_entry.get("doc_slug") if base_entry else None)
        if slug_value in (None, ""):
            slug_value = derive_dir_sync_slug(Path(local["relative_path"]), slug_source, reserved_slugs)
        else:
            slug_value = reserve_unique_slug(str(slug_value), reserved_slugs, local["relative_path"])
        operation["slug"] = slug_value
    if default_public is not None:
        operation["public"] = default_public
    return operation


def build_pull_operation(repo_ref: str, remote: RemoteMarkdownRecord, root_dir: Path) -> Dict[str, Any]:
    output_path = (root_dir / str(remote["relative_path"])).resolve()
    return {
        "command": "pull-markdown",
        "repo": repo_ref,
        "doc": str(remote["doc_id"]),
        "output": str(output_path),
        "front_matter": True,
    }


def public_plan_item(item: SyncPlanItem) -> Dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if not key.startswith("_")
    }


def evaluate_sync_item(
    *,
    repo_ref: str,
    root_dir: Path,
    local: Optional[LocalMarkdownRecord],
    remote: Optional[RemoteMarkdownRecord],
    base_entry: Optional[IndexEntry],
    slug_source: str,
    reserved_slugs: Set[str],
    default_public: Optional[int],
    lookup_by: str,
) -> SyncPlanItem:
    relative_path = (
        local.get("relative_path") if local else None
    ) or (
        remote.get("relative_path") if remote else None
    ) or (
        base_entry.get("relative_path") if base_entry else None
    ) or flat_relative_markdown_path(remote or local or {}, "slug")
    local_path = local.get("absolute_path") if local else str((root_dir / relative_path).resolve())
    doc_id = (remote.get("doc_id") if remote else None) or (local.get("doc_id") if local else None) or (base_entry.get("doc_id") if base_entry else None)
    doc_slug = (remote.get("doc_slug") if remote else None) or (local.get("doc_slug") if local else None) or (base_entry.get("doc_slug") if base_entry else None)
    title = (remote.get("title") if remote else None) or (local.get("title") if local else None) or (base_entry.get("title") if base_entry else None) or Path(relative_path).stem

    local_hash = local.get("content_hash") if local else None
    remote_hash = remote.get("content_hash") if remote else None
    base_hash = base_entry.get("content_hash") if base_entry else None

    item: SyncPlanItem = {
        "status": "skip",
        "reason": "already_in_sync",
        "relative_path": str(relative_path),
        "local_path": str(local_path),
        "doc_id": str(doc_id) if doc_id not in (None, "") else None,
        "doc_slug": str(doc_slug) if doc_slug not in (None, "") else None,
        "title": str(title),
        "local_hash": local_hash,
        "remote_hash": remote_hash,
        "base_hash": base_hash,
        "remote_updated_at": remote.get("updated_at") if remote else None,
        "operation": None,
        "_local": local,
        "_remote": remote,
        "_base_entry": base_entry,
    }

    if local and not remote:
        item["status"] = "push"
        item["reason"] = "missing_remote_doc"
        item["operation"] = build_push_operation(
            repo_ref=repo_ref,
            local=local,
            remote=None,
            base_entry=base_entry,
            slug_source=slug_source,
            reserved_slugs=reserved_slugs,
            default_public=default_public,
            lookup_by=lookup_by,
        )
        return item

    if remote and not local:
        item["status"] = "pull"
        item["reason"] = "missing_local_file"
        item["operation"] = build_pull_operation(repo_ref, remote, root_dir)
        return item

    if local_hash == remote_hash:
        item["status"] = "skip"
        item["reason"] = "content_matches_remote"
        return item

    if base_hash:
        local_changed = local_hash != base_hash
        remote_changed = remote_hash != base_hash
        if local_changed and not remote_changed:
            item["status"] = "push"
            item["reason"] = "local_changed_since_last_sync"
            item["operation"] = build_push_operation(
                repo_ref=repo_ref,
                local=local or {},
                remote=remote,
                base_entry=base_entry,
                slug_source=slug_source,
                reserved_slugs=reserved_slugs,
                default_public=default_public,
                lookup_by=lookup_by,
            )
            return item
        if not local_changed and remote_changed:
            item["status"] = "pull"
            item["reason"] = "remote_changed_since_last_sync"
            item["operation"] = build_pull_operation(repo_ref, remote or {}, root_dir)
            return item
        if local_hash == remote_hash:
            item["status"] = "skip"
            item["reason"] = "content_matches_remote"
            return item
        item["status"] = "conflict"
        item["reason"] = "both_sides_changed_since_last_sync"
        return item

    front_matter_updated_at = local.get("updated_at") if local else None
    remote_updated_at = remote.get("updated_at") if remote else None
    if front_matter_updated_at and remote_updated_at == front_matter_updated_at:
        item["status"] = "push"
        item["reason"] = "local_changed_since_front_matter"
        item["operation"] = build_push_operation(
            repo_ref=repo_ref,
            local=local or {},
            remote=remote,
            base_entry=base_entry,
            slug_source=slug_source,
            reserved_slugs=reserved_slugs,
            default_public=default_public,
            lookup_by=lookup_by,
        )
        return item
    if front_matter_updated_at and local_hash == remote_hash:
        item["status"] = "skip"
        item["reason"] = "content_matches_remote"
        return item

    item["status"] = "conflict"
    item["reason"] = "untracked_divergence"
    return item


def build_dir_sync_plan(
    client: YuqueClient,
    *,
    repo_ref: str,
    root_dir: Path,
    index_file: str,
    name_by: str,
    slug_source: str,
    flat: bool,
    default_public: Optional[int],
    lookup_by: str,
) -> Tuple[DirSyncPlan, DirSyncState]:
    index_path = root_dir / index_file
    index_document = load_index_document(index_path)
    existing_entries = index_entries_from_document(index_document, root_dir)
    index_maps = build_record_maps(existing_entries)

    local_records = load_local_markdown_records(root_dir)
    local_maps = build_record_maps(local_records)
    remote_records = fetch_remote_markdown_records(
        client,
        repo_ref,
        index_maps=index_maps,
        local_maps=local_maps,
        name_by=name_by,
        flat=flat,
    )
    remote_maps = build_record_maps(remote_records)
    reserved_slugs = {
        str(record["doc_slug"])
        for record in remote_records
        if record.get("doc_slug") not in (None, "")
    }

    items: List[SyncPlanItem] = []
    matched_remote_ids: Set[str] = set()
    for local in local_records:
        base_entry = find_base_entry(index_maps, local=local, remote=None)
        remote = (
            find_record(
                remote_maps["by_doc_id"],
                local.get("doc_id"),
                base_entry.get("doc_id") if base_entry else None,
            )
            or find_record(
                remote_maps["by_doc_slug"],
                local.get("doc_slug"),
                base_entry.get("doc_slug") if base_entry else None,
            )
        )
        if remote and remote.get("doc_id"):
            matched_remote_ids.add(str(remote["doc_id"]))
            base_entry = find_base_entry(index_maps, local=local, remote=remote)
        items.append(
            evaluate_sync_item(
                repo_ref=repo_ref,
                root_dir=root_dir,
                local=local,
                remote=remote,
                base_entry=base_entry,
                slug_source=slug_source,
                reserved_slugs=reserved_slugs,
                default_public=default_public,
                lookup_by=lookup_by,
            )
        )

    for remote in remote_records:
        doc_id = str(remote.get("doc_id") or "")
        if doc_id and doc_id in matched_remote_ids:
            continue
        base_entry = find_base_entry(index_maps, local=None, remote=remote)
        items.append(
            evaluate_sync_item(
                repo_ref=repo_ref,
                root_dir=root_dir,
                local=None,
                remote=remote,
                base_entry=base_entry,
                slug_source=slug_source,
                reserved_slugs=reserved_slugs,
                default_public=default_public,
                lookup_by=lookup_by,
            )
        )

    items.sort(key=lambda item: (item.get("relative_path") or "", item.get("doc_id") or ""))
    public_items = [public_plan_item(item) for item in items]
    summary: Dict[str, int] = {}
    for item in public_items:
        summary[item["status"]] = summary.get(item["status"], 0) + 1

    plan: DirSyncPlan = {
        "data": public_items,
        "meta": {
            "repo": repo_ref,
            "root_dir": str(root_dir),
            "index_file": str(index_path),
            "count": len(public_items),
            "summary": summary,
            "index_found": index_path.exists(),
        },
        "operations": [
            item["operation"]
            for item in items
            if item.get("operation") is not None
        ],
    }
    state: DirSyncState = {
        "root_dir": root_dir,
        "index_path": index_path,
        "existing_entries": existing_entries,
        "items": items,
    }
    return plan, state

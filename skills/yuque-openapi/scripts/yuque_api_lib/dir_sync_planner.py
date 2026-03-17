from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .client import YuqueClient
from .dir_sync_records import fetch_remote_markdown_records, find_base_entry, load_local_markdown_records
from .dir_sync_store import build_record_maps, index_entries_from_document, load_index_document
from .dir_sync_types import DirSyncPlan, DirSyncState, IndexEntry, LocalMarkdownRecord, RemoteMarkdownRecord, SyncPlanItem
from .dir_sync_utils import derive_dir_sync_slug, find_record, flat_relative_markdown_path, reserve_unique_slug
from .markdown_docs import normalize_markdown_text


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


REASON_SUMMARY = {
    "missing_remote_doc": "Local markdown exists, but no matching Yuque doc could be found yet.",
    "missing_local_file": "A matching Yuque doc exists, but no local markdown file is present under the compared directory.",
    "content_matches_remote": "Local and remote markdown bodies already match.",
    "local_changed_since_last_sync": "Only the local markdown changed since the last synced hash recorded in yuque-index.json.",
    "remote_changed_since_last_sync": "Only the remote Yuque doc changed since the last synced hash recorded in yuque-index.json.",
    "both_sides_changed_since_last_sync": "Both the local markdown and the remote Yuque doc changed since the last synced hash.",
    "local_changed_since_front_matter": "The local markdown changed while the front matter updated_at still matches the remote updated_at timestamp.",
    "untracked_divergence": "Local and remote markdown differ, but there is no trustworthy base hash for an automatic direction choice.",
}


STATUS_RECOMMENDED_ACTION = {
    "push": "review_then_push",
    "pull": "review_then_pull",
    "conflict": "manual_review",
    "skip": "no_action",
}


def build_review_payload(
    *,
    status: str,
    reason: str,
    local: Optional[LocalMarkdownRecord],
    remote: Optional[RemoteMarkdownRecord],
    base_entry: Optional[IndexEntry],
) -> Dict[str, Any]:
    summary = REASON_SUMMARY.get(reason) or "Review the local and remote markdown states before deciding the next sync step."
    return {
        "recommended_action": STATUS_RECOMMENDED_ACTION.get(status, "review"),
        "summary": summary,
        "local_present": local is not None,
        "remote_present": remote is not None,
        "base_present": base_entry is not None,
    }


def build_diff_preview(
    *,
    relative_path: str,
    doc_id: Optional[str],
    doc_slug: Optional[str],
    local_body: str,
    remote_body: str,
    max_lines: int,
) -> Optional[Dict[str, Any]]:
    normalized_local = normalize_markdown_text(local_body)
    normalized_remote = normalize_markdown_text(remote_body)
    if normalized_local == normalized_remote:
        return None

    remote_label = str(doc_slug or doc_id or "remote")
    diff_lines = list(
        difflib.unified_diff(
            normalized_local.splitlines(),
            normalized_remote.splitlines(),
            fromfile=f"local:{relative_path}",
            tofile=f"yuque:{remote_label}",
            lineterm="",
        )
    )
    if not diff_lines:
        return None

    limited_lines = diff_lines[: max(1, int(max_lines))]
    return {
        "ok": True,
        "format": "unified_diff",
        "line_count": len(diff_lines),
        "truncated": len(diff_lines) > len(limited_lines),
        "preview": "\n".join(limited_lines),
    }


def finalize_sync_item(
    item: SyncPlanItem,
    *,
    local: Optional[LocalMarkdownRecord],
    remote: Optional[RemoteMarkdownRecord],
    base_entry: Optional[IndexEntry],
    include_diff: bool,
    diff_max_lines: int,
) -> SyncPlanItem:
    item["review"] = build_review_payload(
        status=str(item.get("status") or "review"),
        reason=str(item.get("reason") or ""),
        local=local,
        remote=remote,
        base_entry=base_entry,
    )
    if include_diff and local is not None and remote is not None:
        diff_preview = build_diff_preview(
            relative_path=str(item.get("relative_path") or ""),
            doc_id=item.get("doc_id"),
            doc_slug=item.get("doc_slug"),
            local_body=str(local.get("body") or ""),
            remote_body=str(remote.get("body") or ""),
            max_lines=diff_max_lines,
        )
        if diff_preview is not None:
            item["diff_preview"] = diff_preview
    return item


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
    include_diff: bool,
    diff_max_lines: int,
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
        return finalize_sync_item(
            item,
            local=local,
            remote=remote,
            base_entry=base_entry,
            include_diff=include_diff,
            diff_max_lines=diff_max_lines,
        )

    if remote and not local:
        item["status"] = "pull"
        item["reason"] = "missing_local_file"
        item["operation"] = build_pull_operation(repo_ref, remote, root_dir)
        return finalize_sync_item(
            item,
            local=local,
            remote=remote,
            base_entry=base_entry,
            include_diff=include_diff,
            diff_max_lines=diff_max_lines,
        )

    if local_hash == remote_hash:
        item["status"] = "skip"
        item["reason"] = "content_matches_remote"
        return finalize_sync_item(
            item,
            local=local,
            remote=remote,
            base_entry=base_entry,
            include_diff=include_diff,
            diff_max_lines=diff_max_lines,
        )

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
            return finalize_sync_item(
                item,
                local=local,
                remote=remote,
                base_entry=base_entry,
                include_diff=include_diff,
                diff_max_lines=diff_max_lines,
            )
        if not local_changed and remote_changed:
            item["status"] = "pull"
            item["reason"] = "remote_changed_since_last_sync"
            item["operation"] = build_pull_operation(repo_ref, remote or {}, root_dir)
            return finalize_sync_item(
                item,
                local=local,
                remote=remote,
                base_entry=base_entry,
                include_diff=include_diff,
                diff_max_lines=diff_max_lines,
            )
        if local_hash == remote_hash:
            item["status"] = "skip"
            item["reason"] = "content_matches_remote"
            return finalize_sync_item(
                item,
                local=local,
                remote=remote,
                base_entry=base_entry,
                include_diff=include_diff,
                diff_max_lines=diff_max_lines,
            )
        item["status"] = "conflict"
        item["reason"] = "both_sides_changed_since_last_sync"
        return finalize_sync_item(
            item,
            local=local,
            remote=remote,
            base_entry=base_entry,
            include_diff=include_diff,
            diff_max_lines=diff_max_lines,
        )

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
        return finalize_sync_item(
            item,
            local=local,
            remote=remote,
            base_entry=base_entry,
            include_diff=include_diff,
            diff_max_lines=diff_max_lines,
        )
    if front_matter_updated_at and local_hash == remote_hash:
        item["status"] = "skip"
        item["reason"] = "content_matches_remote"
        return finalize_sync_item(
            item,
            local=local,
            remote=remote,
            base_entry=base_entry,
            include_diff=include_diff,
            diff_max_lines=diff_max_lines,
        )

    item["status"] = "conflict"
    item["reason"] = "untracked_divergence"
    return finalize_sync_item(
        item,
        local=local,
        remote=remote,
        base_entry=base_entry,
        include_diff=include_diff,
        diff_max_lines=diff_max_lines,
    )


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
    include_diff: bool = False,
    diff_max_lines: int = 80,
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
                include_diff=include_diff,
                diff_max_lines=diff_max_lines,
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
                include_diff=include_diff,
                diff_max_lines=diff_max_lines,
            )
        )

    items.sort(key=lambda item: (item.get("relative_path") or "", item.get("doc_id") or ""))
    public_items = [public_plan_item(item) for item in items]
    summary: Dict[str, int] = {}
    for item in public_items:
        summary[item["status"]] = summary.get(item["status"], 0) + 1
    review_summary = {
        "diff_enabled": include_diff,
        "diff_generated_count": sum(1 for item in public_items if isinstance(item.get("diff_preview"), dict) and item["diff_preview"].get("ok")),
        "manual_review_count": sum(1 for item in public_items if item.get("review", {}).get("recommended_action") == "manual_review"),
        "push_review_count": sum(1 for item in public_items if item.get("review", {}).get("recommended_action") == "review_then_push"),
        "pull_review_count": sum(1 for item in public_items if item.get("review", {}).get("recommended_action") == "review_then_pull"),
    }

    plan: DirSyncPlan = {
        "data": public_items,
        "meta": {
            "repo": repo_ref,
            "root_dir": str(root_dir),
            "index_file": str(index_path),
            "count": len(public_items),
            "summary": summary,
            "index_found": index_path.exists(),
            "review": review_summary,
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

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, TypedDict, cast

from .client import YuqueClient, build_repo_path, fetch_repo_detail, fetch_repo_doc_summaries, fetch_repo_toc, unwrap_data
from .core import DEFAULT_INDEX_FILE, SNAPSHOT_SCHEMA_VERSION, YuqueApiError, emit_progress
from .dir_sync import IndexEntry, LocalMarkdownRecord, RecordMaps, build_record_maps, find_base_entry, find_record, index_entries_from_document, load_index_document, load_local_markdown_records
from .markdown_docs import current_utc_timestamp, derive_markdown_title, ensure_parent_dir, export_repo_markdown_bundle, front_matter_text, push_markdown_file, sanitize_filename, split_front_matter


class MissingRemoteDoc(TypedDict, total=False):
    id: Any
    slug: str
    title: str


class ResolvedTocDoc(TypedDict):
    title: str
    slug: str
    doc_id: str


class RepoTocPlan(TypedDict):
    root_dir: str
    index_file: str
    toc_markdown: str
    entry_count: int
    missing_remote_docs: List[MissingRemoteDoc]


class SnapshotMetadata(TypedDict, total=False):
    schema_version: int
    repo: str
    reason: str
    created_at: str
    local_root_dir: str
    snapshot_dir: str
    docs_dir: str
    docs_index_file: str
    doc_count: int
    repo_file: str
    toc_file: str
    toc_markdown_file: str
    repo_id: Any
    repo_slug: str
    repo_name: str
    metadata_file: str


class TocSyncResult(TypedDict, total=False):
    repo: str
    root_dir: str
    index_file: str
    entry_count: int
    pruned_remote_doc_count: int
    updated_at: Any
    pruned_remote_docs: List[MissingRemoteDoc]
    toc_file: str
    backup: SnapshotMetadata
    backup_skipped: bool


class SnapshotRestoreExecution(TypedDict, total=False):
    action: str
    path: str
    doc_id: Any
    doc_slug: Optional[str]
    title: Optional[str]
    source: str


class SnapshotRestoreResult(TypedDict, total=False):
    dry_run: bool
    repo: str
    snapshot_dir: str
    metadata_file: str
    docs_dir: str
    restored_doc_count: int
    restored_docs: List[SnapshotRestoreExecution]
    toc_restored: bool
    toc_entry_count: int
    updated_at: Any
    override_used: bool
    toc_file: str
    schema_version: int


def build_unique_title_map(records: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    unique: Dict[str, Dict[str, Any]] = {}
    duplicate_titles: set[str] = set()
    for record in records:
        title = str(record.get("title") or "")
        if not title:
            continue
        if title in unique:
            duplicate_titles.add(title)
            continue
        unique[title] = record
    for title in duplicate_titles:
        unique.pop(title, None)
    return unique


def render_remote_toc_markdown(toc_items: Sequence[Dict[str, Any]]) -> str:
    children_by_parent: Dict[str, List[Dict[str, Any]]] = {}
    for item in toc_items:
        parent_uuid = str(item.get("parent_uuid") or "")
        children_by_parent.setdefault(parent_uuid, []).append(item)

    lines: List[str] = []

    def render(parent_uuid: str, depth: int) -> None:
        for item in children_by_parent.get(parent_uuid, []):
            title = str(
                item.get("title")
                or item.get("name")
                or item.get("slug")
                or item.get("doc_id")
                or item.get("id")
                or "doc"
            )
            target = str(item.get("slug") or item.get("doc_id") or item.get("id") or "")
            if not target:
                continue
            lines.append(f"{'  ' * depth}- [{title}]({target})")
            render(str(item.get("uuid") or ""), depth + 1)

    render("", 0)
    return "\n".join(lines) + ("\n" if lines else "")


def count_toc_entries(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if line.lstrip().startswith("- "))


def resolve_local_toc_doc(
    local_record: LocalMarkdownRecord,
    *,
    index_maps: RecordMaps,
    remote_docs_by_id: Dict[str, Dict[str, Any]],
    remote_docs_by_slug: Dict[str, Dict[str, Any]],
    remote_docs_by_title: Dict[str, Dict[str, Any]],
) -> ResolvedTocDoc:
    base_entry = find_base_entry(index_maps, local=local_record, remote=None) or {}
    remote = (
        find_record(
            remote_docs_by_id,
            local_record.get("doc_id"),
            base_entry.get("doc_id"),
        )
        or find_record(
            remote_docs_by_slug,
            local_record.get("doc_slug"),
            base_entry.get("doc_slug"),
        )
    )
    if remote is None:
        title = str(local_record.get("title") or "")
        remote = remote_docs_by_title.get(title)

    title_value = (
        str(local_record.get("title") or "")
        or str((remote or {}).get("title") or "")
        or str(base_entry.get("title") or "")
    )
    slug_value = (
        str((remote or {}).get("slug") or "")
        or str(local_record.get("doc_slug") or "")
        or str(base_entry.get("doc_slug") or "")
    )
    doc_id_value = (
        str((remote or {}).get("id") or "")
        or str(local_record.get("doc_id") or "")
        or str(base_entry.get("doc_id") or "")
    )

    if not title_value:
        raise YuqueApiError(
            f"Unable to resolve a TOC title for local markdown file {local_record.get('relative_path')}."
        )
    if not slug_value:
        raise YuqueApiError(
            "Unable to resolve a Yuque doc slug while building the TOC for "
            f"{local_record.get('relative_path')}. Pull the repo first or refresh {DEFAULT_INDEX_FILE}."
        )
    return {
        "title": title_value,
        "slug": slug_value,
        "doc_id": doc_id_value,
    }


def toc_sort_key(path: Path) -> tuple[int, int, str]:
    return (
        0 if path.is_dir() else 1,
        0 if path.name.lower() == "index.md" else 1,
        path.name.lower(),
    )


def render_local_toc_lines(
    current_path: Path,
    *,
    root_dir: Path,
    record_map: Dict[str, ResolvedTocDoc],
    depth: int,
) -> List[str]:
    if current_path.is_dir():
        entries = sorted(current_path.iterdir(), key=toc_sort_key)
        index_path = current_path / "index.md"
        if index_path.exists():
            relative_index = index_path.relative_to(root_dir).as_posix()
            record = record_map.get(relative_index)
            if record is None:
                raise YuqueApiError(
                    f"Missing TOC mapping for local index file {relative_index}."
                )
            lines = [f"{'  ' * depth}- [{record['title']}]({record['slug']})"]
            for entry in entries:
                if entry.name.lower() == "index.md":
                    continue
                lines.extend(
                    render_local_toc_lines(
                        entry,
                        root_dir=root_dir,
                        record_map=record_map,
                        depth=depth + 1,
                    )
                )
            return lines

        lines: List[str] = []
        for entry in entries:
            lines.extend(
                render_local_toc_lines(
                    entry,
                    root_dir=root_dir,
                    record_map=record_map,
                    depth=depth,
                )
            )
        return lines

    if current_path.suffix.lower() != ".md":
        return []
    if current_path == root_dir / "index.md":
        return []

    relative_path = current_path.relative_to(root_dir).as_posix()
    record = record_map.get(relative_path)
    if record is None:
        raise YuqueApiError(f"Missing TOC mapping for local markdown file {relative_path}.")
    return [f"{'  ' * depth}- [{record['title']}]({record['slug']})"]


def build_repo_toc_markdown_from_local_dir(
    client: YuqueClient,
    *,
    repo_ref: str,
    root_dir: Path,
    index_file: str,
) -> RepoTocPlan:
    if not root_dir.exists():
        raise YuqueApiError(f"Root directory does not exist: {root_dir}")

    index_path = root_dir / index_file
    index_document = load_index_document(index_path)
    index_entries = index_entries_from_document(index_document, root_dir)
    index_maps = build_record_maps(index_entries)
    local_records = load_local_markdown_records(root_dir)
    if not local_records:
        raise YuqueApiError(f"No markdown files found under {root_dir}.")

    remote_docs = fetch_repo_doc_summaries(client, repo_ref)
    remote_docs_by_id = {
        str(doc.get("id")): doc
        for doc in remote_docs
        if doc.get("id") not in (None, "")
    }
    remote_docs_by_slug = {
        str(doc.get("slug")): doc
        for doc in remote_docs
        if doc.get("slug") not in (None, "")
    }
    remote_docs_by_title = build_unique_title_map(remote_docs)

    record_map: Dict[str, ResolvedTocDoc] = {}
    for local_record in local_records:
        relative_path = str(local_record.get("relative_path") or "")
        if not relative_path:
            continue
        record_map[relative_path] = resolve_local_toc_doc(
            local_record,
            index_maps=index_maps,
            remote_docs_by_id=remote_docs_by_id,
            remote_docs_by_slug=remote_docs_by_slug,
            remote_docs_by_title=remote_docs_by_title,
        )

    lines: List[str] = []
    for entry in sorted(root_dir.iterdir(), key=toc_sort_key):
        if entry.name == index_file:
            continue
        lines.extend(
            render_local_toc_lines(
                entry,
                root_dir=root_dir,
                record_map=record_map,
                depth=0,
            )
        )
    if not lines:
        raise YuqueApiError(f"No TOC entries could be built from {root_dir}.")
    included_doc_ids = {
        str(record.get("doc_id"))
        for record in record_map.values()
        if record.get("doc_id") not in (None, "")
    }
    included_doc_slugs = {
        str(record.get("slug"))
        for record in record_map.values()
        if record.get("slug") not in (None, "")
    }
    missing_remote_docs: List[MissingRemoteDoc] = []
    for doc in remote_docs:
        doc_id = str(doc.get("id") or "")
        doc_slug = str(doc.get("slug") or "")
        if (doc_id and doc_id in included_doc_ids) or (doc_slug and doc_slug in included_doc_slugs):
            continue
        missing_remote_docs.append(
            {
                "id": doc.get("id"),
                "slug": str(doc.get("slug") or ""),
                "title": str(doc.get("title") or ""),
            }
        )
    return {
        "root_dir": str(root_dir),
        "index_file": str(index_path),
        "toc_markdown": "\n".join(lines) + "\n",
        "entry_count": len(lines),
        "missing_remote_docs": missing_remote_docs,
    }


def sync_repo_toc_from_local_dir(
    client: YuqueClient,
    *,
    repo_ref: str,
    root_dir: Path,
    index_file: str,
    write_toc_file: Optional[str],
    allow_prune: bool,
    backup_dir: Optional[str],
    skip_backup: bool,
) -> TocSyncResult:
    toc_plan = build_repo_toc_markdown_from_local_dir(
        client,
        repo_ref=repo_ref,
        root_dir=root_dir,
        index_file=index_file,
    )
    missing_remote_docs = list(toc_plan.get("missing_remote_docs") or [])
    if missing_remote_docs and not allow_prune:
        preview = ", ".join(
            f"{item.get('title') or item.get('slug') or item.get('id')}"
            for item in missing_remote_docs[:5]
        )
        if len(missing_remote_docs) > 5:
            preview += ", ..."
        raise YuqueApiError(
            "Refusing to rewrite the repo TOC because some remote docs are missing from the local markdown tree. "
            f"Missing remote docs: {preview}. Pull the full repo first or re-run with --allow-prune if removal is intended."
        )
    backup_result: Optional[SnapshotMetadata] = None
    if not skip_backup:
        backup_result = create_repo_snapshot_backup(
            client,
            repo_ref=repo_ref,
            root_dir=root_dir,
            backup_dir=backup_dir,
            reason="before_toc_sync",
        )
    toc_markdown = str(toc_plan["toc_markdown"])
    toc_file_path: Optional[Path] = None
    if write_toc_file:
        toc_file_path = Path(write_toc_file)
        ensure_parent_dir(toc_file_path)
        toc_file_path.write_text(toc_markdown, encoding="utf-8")

    response = client.request(
        "PUT",
        build_repo_path(repo_ref),
        payload={"toc": toc_markdown},
    )
    repo = unwrap_data(response)
    if not isinstance(repo, dict):
        raise YuqueApiError("Expected repo object while updating the repo TOC.")

    result: TocSyncResult = {
        "repo": repo_ref,
        "root_dir": toc_plan["root_dir"],
        "index_file": toc_plan["index_file"],
        "entry_count": toc_plan["entry_count"],
        "pruned_remote_doc_count": len(missing_remote_docs),
        "updated_at": repo.get("updated_at"),
    }
    if missing_remote_docs:
        result["pruned_remote_docs"] = missing_remote_docs
    if toc_file_path is not None:
        result["toc_file"] = str(toc_file_path)
    if backup_result is not None:
        result["backup"] = backup_result
    else:
        result["backup_skipped"] = True
    return result


def allocate_repo_snapshot_dir(base_dir: Path, repo_ref: str) -> Path:
    repo_segment = sanitize_filename(repo_ref.replace("/", "__"))
    timestamp = time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())
    repo_dir = base_dir / repo_segment
    candidate = repo_dir / timestamp
    suffix = 2
    while candidate.exists():
        candidate = repo_dir / f"{timestamp}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def create_repo_snapshot_backup(
    client: YuqueClient,
    *,
    repo_ref: str,
    root_dir: Path,
    backup_dir: Optional[str],
    reason: str,
) -> SnapshotMetadata:
    base_dir = Path(backup_dir) if backup_dir else root_dir.parent / ".yuque-backups"
    snapshot_dir = allocate_repo_snapshot_dir(base_dir, repo_ref)
    repo = fetch_repo_detail(client, repo_ref)
    toc_items = fetch_repo_toc(client, repo_ref)
    export_result = export_repo_markdown_bundle(
        client,
        repo_ref=repo_ref,
        export_dir=snapshot_dir / "docs",
        front_matter=True,
        index_file=DEFAULT_INDEX_FILE,
        name_by="slug",
    )

    repo_file = snapshot_dir / "repo.json"
    repo_file.write_text(
        json.dumps(repo, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    toc_file = snapshot_dir / "toc.json"
    toc_file.write_text(
        json.dumps(toc_items, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    toc_markdown_file = snapshot_dir / "toc.md"
    toc_markdown_file.write_text(render_remote_toc_markdown(toc_items), encoding="utf-8")

    metadata: SnapshotMetadata = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "repo": repo_ref,
        "reason": reason,
        "created_at": current_utc_timestamp(),
        "local_root_dir": str(root_dir),
        "snapshot_dir": str(snapshot_dir),
        "docs_dir": export_result["output_dir"],
        "docs_index_file": export_result["index_file"],
        "doc_count": export_result["count"],
        "repo_file": str(repo_file),
        "toc_file": str(toc_file),
        "toc_markdown_file": str(toc_markdown_file),
        "repo_id": repo.get("id"),
        "repo_slug": repo.get("slug"),
        "repo_name": repo.get("name"),
    }
    metadata_file = snapshot_dir / "snapshot.json"
    metadata_file.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    metadata["metadata_file"] = str(metadata_file)
    return metadata


def resolve_snapshot_metadata_file(snapshot_path: Path) -> Path:
    if snapshot_path.is_dir():
        return snapshot_path / "snapshot.json"
    return snapshot_path


def load_snapshot_metadata(snapshot_path: Path) -> SnapshotMetadata:
    metadata_file = resolve_snapshot_metadata_file(snapshot_path)
    if not metadata_file.exists():
        raise YuqueApiError(f"Snapshot metadata file does not exist: {metadata_file}")
    try:
        parsed = json.loads(metadata_file.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise YuqueApiError(f"Snapshot metadata must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise YuqueApiError("Snapshot metadata must be a JSON object.")
    metadata = cast(SnapshotMetadata, dict(parsed))
    schema_version = metadata.get("schema_version")
    if schema_version in (None, ""):
        metadata["schema_version"] = SNAPSHOT_SCHEMA_VERSION
    elif schema_version != SNAPSHOT_SCHEMA_VERSION:
        raise YuqueApiError(
            f"Unsupported snapshot schema_version {schema_version}. This tool supports schema_version {SNAPSHOT_SCHEMA_VERSION}."
        )
    metadata["metadata_file"] = str(metadata_file)
    if not metadata.get("snapshot_dir"):
        metadata["snapshot_dir"] = str(metadata_file.parent)
    return metadata


def snapshot_file_path(metadata: SnapshotMetadata, key: str, *, fallback: str) -> Path:
    snapshot_dir = Path(str(metadata.get("snapshot_dir") or ""))
    value = metadata.get(key)
    if value not in (None, ""):
        return Path(str(value))
    return snapshot_dir / fallback


def iter_snapshot_markdown_files(docs_dir: Path) -> List[Path]:
    if not docs_dir.exists():
        raise YuqueApiError(f"Snapshot docs directory does not exist: {docs_dir}")
    files = [path for path in docs_dir.rglob("*.md") if path.is_file()]
    if not files:
        raise YuqueApiError(f"No markdown files found in snapshot docs directory: {docs_dir}")
    return sorted(files)


def preview_snapshot_restore_docs(docs_dir: Path) -> List[SnapshotRestoreExecution]:
    previews: List[SnapshotRestoreExecution] = []
    for doc_path in iter_snapshot_markdown_files(docs_dir):
        raw_markdown = doc_path.read_text(encoding="utf-8")
        front_matter, body = split_front_matter(raw_markdown)
        previews.append(
            {
                "action": "would_restore",
                "path": str(doc_path),
                "doc_id": front_matter_text(front_matter, "yuque_doc_id"),
                "doc_slug": front_matter_text(front_matter, "yuque_doc_slug"),
                "title": front_matter_text(front_matter, "title") or derive_markdown_title(body, doc_path.stem),
                "source": "snapshot_markdown",
            }
        )
    return previews


def restore_repo_snapshot(
    client: YuqueClient,
    *,
    snapshot_path: Path,
    repo_ref: Optional[str],
    allow_repo_override: bool,
    skip_docs: bool,
    skip_toc: bool,
    dry_run: bool,
    write_toc_file: Optional[str],
) -> SnapshotRestoreResult:
    if skip_docs and skip_toc:
        raise YuqueApiError("Nothing to restore. Re-run without --skip-docs or --skip-toc.")

    metadata = load_snapshot_metadata(snapshot_path)
    snapshot_repo = str(metadata.get("repo") or "")
    target_repo = repo_ref or snapshot_repo
    if not target_repo:
        raise YuqueApiError("Unable to determine the target repo from the snapshot metadata. Pass --repo explicitly.")
    override_used = bool(repo_ref and snapshot_repo and repo_ref != snapshot_repo)
    if override_used and not allow_repo_override:
        raise YuqueApiError(
            f"Snapshot was created for {snapshot_repo}, but --repo requested {repo_ref}. Re-run with --allow-repo-override if this is intentional."
        )

    snapshot_dir = Path(str(metadata.get("snapshot_dir") or ""))
    docs_dir = snapshot_file_path(metadata, "docs_dir", fallback="docs")
    toc_markdown_file = snapshot_file_path(metadata, "toc_markdown_file", fallback="toc.md")

    restored_docs: List[SnapshotRestoreExecution] = []
    if not skip_docs:
        markdown_files = iter_snapshot_markdown_files(docs_dir)
        if dry_run:
            restored_docs = preview_snapshot_restore_docs(docs_dir)
        else:
            total_docs = len(markdown_files)
            for index, doc_path in enumerate(markdown_files, start=1):
                emit_progress(f"[restore docs {index}/{total_docs}] {doc_path.name}")
                result = push_markdown_file(
                    client,
                    repo_ref=target_repo,
                    source_path=doc_path,
                    doc_ref=None,
                    title=None,
                    slug=None,
                    public=None,
                    lookup_by="auto",
                    keep_front_matter=False,
                    extra_json=None,
                )
                restored_docs.append(
                    {
                        "action": str(result.get("action") or ""),
                        "path": str(doc_path),
                        "doc_id": result.get("doc_id"),
                        "doc_slug": cast(Optional[str], result.get("doc_slug")),
                        "title": cast(Optional[str], result.get("title")),
                        "source": "snapshot_markdown",
                    }
                )
                emit_progress(f"[restore docs {index}/{total_docs}] done")

    updated_at: Any = None
    toc_entry_count = 0
    toc_file_path: Optional[Path] = None
    if not skip_toc:
        if not toc_markdown_file.exists():
            raise YuqueApiError(f"Snapshot TOC markdown file does not exist: {toc_markdown_file}")
        toc_markdown = toc_markdown_file.read_text(encoding="utf-8")
        toc_entry_count = count_toc_entries(toc_markdown)
        if write_toc_file:
            toc_file_path = Path(write_toc_file)
            ensure_parent_dir(toc_file_path)
            toc_file_path.write_text(toc_markdown, encoding="utf-8")
        if not dry_run:
            emit_progress(f"[restore toc] applying {toc_entry_count} entries")
            response = client.request(
                "PUT",
                build_repo_path(target_repo),
                payload={"toc": toc_markdown},
            )
            repo = unwrap_data(response)
            if not isinstance(repo, dict):
                raise YuqueApiError("Expected repo object while restoring the snapshot TOC.")
            updated_at = repo.get("updated_at")
            emit_progress(f"[restore toc] done entries={toc_entry_count}")

    result: SnapshotRestoreResult = {
        "dry_run": dry_run,
        "repo": target_repo,
        "snapshot_dir": str(snapshot_dir),
        "metadata_file": str(metadata.get("metadata_file") or resolve_snapshot_metadata_file(snapshot_path)),
        "docs_dir": str(docs_dir),
        "restored_doc_count": len(restored_docs),
        "restored_docs": restored_docs,
        "toc_restored": not skip_toc,
        "toc_entry_count": toc_entry_count,
        "updated_at": updated_at,
        "override_used": override_used,
        "schema_version": int(metadata.get("schema_version") or SNAPSHOT_SCHEMA_VERSION),
    }
    if toc_file_path is not None:
        result["toc_file"] = str(toc_file_path)
    mode = "preview" if dry_run else "restore"
    emit_progress(
        f"[{mode} snapshot] docs={len(restored_docs)} toc_entries={toc_entry_count} target={target_repo}"
    )
    return result

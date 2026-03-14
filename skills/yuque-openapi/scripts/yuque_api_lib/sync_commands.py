from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from .client import YuqueClient, unwrap_data
from .command_builders import configure_repo_only
from .command_types import CommandSpec, OperationDispatcher
from .core import DEFAULT_INDEX_FILE, YuqueApiError, emit_progress
from .dir_sync import DirSyncState, IndexEntry, SyncPlanItem, build_dir_sync_plan, build_sync_index_entry, merge_index_entries, public_plan_item, write_sync_index
from .markdown_docs import ensure_parent_dir
from .toc_sync import SnapshotRestoreResult, TocSyncResult, restore_repo_snapshot, sync_repo_toc_from_local_dir


class DirectionalSyncExecution(TypedDict, total=False):
    status: str
    relative_path: str
    doc_id: Optional[str]
    title: Optional[str]
    result: Any


class DirectionalSyncOutput(TypedDict):
    executed: List[DirectionalSyncExecution]
    blocked: List[Dict[str, Any]]


def _execute_directional_sync(
    client: YuqueClient,
    *,
    repo_ref: str,
    state: DirSyncState,
    target_status: str,
    dispatch_operation: OperationDispatcher,
) -> DirectionalSyncOutput:
    executed: List[DirectionalSyncExecution] = []
    updated_entries: List[IndexEntry] = []
    blocked: List[Dict[str, Any]] = []
    executable_items = [
        item
        for item in state["items"]
        if item["status"] == target_status and item.get("operation")
    ]
    total = len(executable_items)
    completed = 0

    for item in state["items"]:
        operation = item.get("operation")
        if item["status"] == target_status and operation:
            completed += 1
            emit_progress(
                f"[{target_status} {completed}/{total}] {item.get('relative_path') or item.get('doc_id') or '<unknown>'}"
            )
            result = dispatch_operation(client, operation)
            result_data = unwrap_data(result)
            result_doc = result_data if isinstance(result_data, dict) else None
            executed.append(
                {
                    "status": target_status,
                    "relative_path": str(item["relative_path"]),
                    "doc_id": (result_doc or {}).get("doc_id") or item.get("doc_id"),
                    "title": (result_doc or {}).get("title") or item.get("title"),
                    "result": result_data,
                }
            )
            updated_entries.append(build_sync_index_entry(item, result_data=result_doc))
            emit_progress(
                f"[{target_status} {completed}/{total}] done ok={len(executed)} blocked={len(blocked)}"
            )
        elif item["status"] == "skip":
            updated_entries.append(build_sync_index_entry(item))
        else:
            blocked.append(public_plan_item(item))

    merged_entries = merge_index_entries(state["existing_entries"], updated_entries)
    write_sync_index(state["index_path"], repo_ref, merged_entries)
    emit_progress(
        f"[{target_status} summary] executed={len(executed)} blocked={len(blocked)} index={state['index_path']}"
    )
    return {
        "executed": executed,
        "blocked": blocked,
    }


def handle_plan_dir_markdown(client: YuqueClient, args: argparse.Namespace) -> Any:
    root_dir = Path(args.root_dir)
    plan, _state = build_dir_sync_plan(
        client,
        repo_ref=args.repo,
        root_dir=root_dir,
        index_file=args.index_file,
        name_by=args.name_by,
        slug_source=args.slug_source,
        flat=args.flat,
        default_public=None,
        lookup_by="auto",
    )
    if args.write_manifest:
        manifest_path = Path(args.write_manifest)
        ensure_parent_dir(manifest_path)
        manifest_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        plan["meta"]["manifest_path"] = str(manifest_path)
    return plan


def handle_sync_dir_toc(client: YuqueClient, args: argparse.Namespace) -> Dict[str, TocSyncResult]:
    return {
        "data": sync_repo_toc_from_local_dir(
            client,
            repo_ref=args.repo,
            root_dir=Path(args.root_dir),
            index_file=args.index_file,
            write_toc_file=args.write_toc_file,
            allow_prune=args.allow_prune,
            backup_dir=args.backup_dir,
            skip_backup=args.skip_backup,
        )
    }


def handle_restore_repo_snapshot(client: YuqueClient, args: argparse.Namespace) -> Dict[str, SnapshotRestoreResult]:
    return {
        "data": restore_repo_snapshot(
            client,
            snapshot_path=Path(args.snapshot),
            repo_ref=args.repo,
            allow_repo_override=args.allow_repo_override,
            skip_docs=args.skip_docs,
            skip_toc=args.skip_toc,
            dry_run=args.dry_run,
            write_toc_file=args.write_toc_file,
        )
    }


def handle_pull_dir_markdown(client: YuqueClient, args: argparse.Namespace, *, dispatch_operation: OperationDispatcher) -> Any:
    root_dir = Path(args.output_dir)
    plan, state = build_dir_sync_plan(
        client,
        repo_ref=args.repo,
        root_dir=root_dir,
        index_file=args.index_file,
        name_by=args.name_by,
        slug_source="path",
        flat=args.flat,
        default_public=None,
        lookup_by="auto",
    )

    sync_output = _execute_directional_sync(
        client,
        repo_ref=args.repo,
        state=state,
        target_status="pull",
        dispatch_operation=dispatch_operation,
    )
    return {
        "data": sync_output,
        "meta": {
            "repo": args.repo,
            "root_dir": str(root_dir),
            "index_file": str(state["index_path"]),
            "executed_count": len(sync_output["executed"]),
            "blocked_count": len(sync_output["blocked"]),
            "plan_summary": plan["meta"]["summary"],
        },
    }


def handle_push_dir_markdown(client: YuqueClient, args: argparse.Namespace, *, dispatch_operation: OperationDispatcher) -> Any:
    root_dir = Path(args.source_dir)
    if not root_dir.exists():
        raise YuqueApiError(f"Source directory does not exist: {root_dir}")

    plan, state = build_dir_sync_plan(
        client,
        repo_ref=args.repo,
        root_dir=root_dir,
        index_file=args.index_file,
        name_by="title",
        slug_source=args.slug_source,
        flat=False,
        default_public=args.public,
        lookup_by=args.lookup_by,
    )

    sync_output = _execute_directional_sync(
        client,
        repo_ref=args.repo,
        state=state,
        target_status="push",
        dispatch_operation=dispatch_operation,
    )
    toc_result: Optional[TocSyncResult] = None
    if args.sync_toc:
        toc_result = sync_repo_toc_from_local_dir(
            client,
            repo_ref=args.repo,
            root_dir=root_dir,
            index_file=args.index_file,
            write_toc_file=args.write_toc_file,
            allow_prune=args.allow_prune,
            backup_dir=args.backup_dir,
            skip_backup=args.skip_backup,
        )
    return {
        "data": {
            "executed": sync_output["executed"],
            "blocked": sync_output["blocked"],
            "toc": toc_result,
        },
        "meta": {
            "repo": args.repo,
            "root_dir": str(root_dir),
            "index_file": str(state["index_path"]),
            "executed_count": len(sync_output["executed"]),
            "blocked_count": len(sync_output["blocked"]),
            "plan_summary": plan["meta"]["summary"],
        },
    }


def configure_push_dir_markdown(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    parser.add_argument("source_dir", help="Local directory that contains markdown files.")
    parser.add_argument("--index-file", default=DEFAULT_INDEX_FILE, help=f"Manifest filename kept inside the source directory. Defaults to {DEFAULT_INDEX_FILE}.")
    parser.add_argument("--slug-source", choices=("path", "stem"), default="path", help="How to derive slugs for brand-new docs without an existing mapping. Defaults to path.")
    parser.add_argument("--public", type=int, choices=(0, 1), help="Default public visibility flag for brand-new docs when local metadata does not provide one.")
    parser.add_argument("--lookup-by", choices=("auto", "slug", "id"), default="auto", help="How to treat existing doc lookups when a file already carries a Yuque doc reference.")
    parser.add_argument("--sync-toc", action="store_true", help="After pushing, rewrite the remote Yuque TOC from the local markdown directory tree.")
    parser.add_argument("--write-toc-file", help="Optional path to write the generated TOC markdown when syncing the remote TOC.")
    parser.add_argument("--allow-prune", action="store_true", help="Allow --sync-toc to drop remote docs that are not represented by the local markdown tree.")
    parser.add_argument("--backup-dir", help="Base directory for the automatic repo snapshot taken before --sync-toc updates the remote TOC.")
    parser.add_argument("--skip-backup", action="store_true", help="Skip the automatic repo snapshot that normally runs before --sync-toc updates the remote TOC.")


def configure_pull_dir_markdown(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    parser.add_argument("output_dir", help="Local directory that receives markdown files.")
    parser.add_argument("--index-file", default=DEFAULT_INDEX_FILE, help=f"Manifest filename kept inside the output directory. Defaults to {DEFAULT_INDEX_FILE}.")
    parser.add_argument("--name-by", choices=("slug", "title", "id"), default="title", help="Fallback naming mode when no prior path mapping is available. Defaults to title.")
    parser.add_argument("--flat", action="store_true", help="Ignore Yuque TOC nesting and export files flat under the output directory.")


def configure_plan_dir_markdown(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    parser.add_argument("root_dir", help="Local markdown directory to compare against the repo.")
    parser.add_argument("--index-file", default=DEFAULT_INDEX_FILE, help=f"Manifest filename kept inside the root directory. Defaults to {DEFAULT_INDEX_FILE}.")
    parser.add_argument("--name-by", choices=("slug", "title", "id"), default="title", help="Fallback naming mode when no prior path mapping is available. Defaults to title.")
    parser.add_argument("--slug-source", choices=("path", "stem"), default="path", help="How to derive slugs for brand-new docs without an existing mapping. Defaults to path.")
    parser.add_argument("--flat", action="store_true", help="Ignore Yuque TOC nesting and build flat fallback paths under the root directory.")
    parser.add_argument("--write-manifest", help="Optional path to write the generated sync manifest JSON.")


def configure_sync_dir_toc(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    parser.add_argument("root_dir", help="Local markdown directory whose tree defines the TOC.")
    parser.add_argument("--index-file", default=DEFAULT_INDEX_FILE, help=f"Manifest filename kept inside the root directory. Defaults to {DEFAULT_INDEX_FILE}.")
    parser.add_argument("--write-toc-file", help="Optional path to write the generated TOC markdown before uploading it.")
    parser.add_argument("--allow-prune", action="store_true", help="Allow the TOC sync to drop remote docs that are not represented by the local markdown tree.")
    parser.add_argument("--backup-dir", help="Base directory for the automatic repo snapshot taken before the remote TOC is rewritten.")
    parser.add_argument("--skip-backup", action="store_true", help="Skip the automatic repo snapshot that normally runs before the remote TOC is rewritten.")


def configure_restore_repo_snapshot(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("snapshot", help="Path to a snapshot directory or its snapshot.json metadata file.")
    parser.add_argument("--repo", help="Override the snapshot target repo. Defaults to the repo stored in snapshot.json.")
    parser.add_argument("--allow-repo-override", action="store_true", help="Allow --repo to differ from the repo stored in the snapshot metadata.")
    parser.add_argument("--skip-docs", action="store_true", help="Restore only the TOC from the snapshot.")
    parser.add_argument("--skip-toc", action="store_true", help="Restore only markdown docs from the snapshot.")
    parser.add_argument("--dry-run", action="store_true", help="Preview which docs and TOC entries would be restored without writing to Yuque.")
    parser.add_argument("--write-toc-file", help="Optional path to write the restored TOC markdown locally before uploading it.")


def build_sync_command_specs(dispatch_operation: OperationDispatcher) -> Tuple[CommandSpec, ...]:
    return (
        CommandSpec("plan-dir-markdown", "Build a bidirectional incremental sync manifest for a repo and local markdown directory.", handle_plan_dir_markdown, configure_plan_dir_markdown, {"index_file": DEFAULT_INDEX_FILE, "name_by": "title", "slug_source": "path", "flat": False, "write_manifest": None}),
        CommandSpec("sync-dir-toc", "Rewrite a Yuque repo TOC from a local markdown directory tree.", handle_sync_dir_toc, configure_sync_dir_toc, {"index_file": DEFAULT_INDEX_FILE, "write_toc_file": None, "allow_prune": False, "backup_dir": None, "skip_backup": False}),
        CommandSpec("restore-repo-snapshot", "Restore docs and/or TOC from an automatic repo snapshot.", handle_restore_repo_snapshot, configure_restore_repo_snapshot, {"repo": None, "allow_repo_override": False, "skip_docs": False, "skip_toc": False, "dry_run": False, "write_toc_file": None}),
        CommandSpec("pull-dir-markdown", "Sync a Yuque repo into a local markdown directory, preserving known structure.", lambda client, args: handle_pull_dir_markdown(client, args, dispatch_operation=dispatch_operation), configure_pull_dir_markdown, {"index_file": DEFAULT_INDEX_FILE, "name_by": "title", "flat": False}),
        CommandSpec("push-dir-markdown", "Recursively sync a local markdown directory into a Yuque repo.", lambda client, args: handle_push_dir_markdown(client, args, dispatch_operation=dispatch_operation), configure_push_dir_markdown, {"index_file": DEFAULT_INDEX_FILE, "slug_source": "path", "public": None, "lookup_by": "auto", "sync_toc": False, "write_toc_file": None, "allow_prune": False, "backup_dir": None, "skip_backup": False}),
    )

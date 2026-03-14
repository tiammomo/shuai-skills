#!/usr/bin/env python3
"""Cross-platform helper CLI for Yuque OpenAPI workflows."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from yuque_api_lib import YuqueApiError, YuqueClient, build_repo_toc_markdown_from_local_dir, main, restore_repo_snapshot, sync_repo_toc_from_local_dir
from yuque_api_lib.commands import build_parser, namespace_from_operation, perform_command
from yuque_api_lib.markdown_sync import export_repo_markdown_bundle
from yuque_api_lib.toc_sync import create_repo_snapshot_backup

__all__ = [
    "YuqueApiError",
    "YuqueClient",
    "build_repo_toc_markdown_from_local_dir",
    "build_parser",
    "create_repo_snapshot_backup",
    "export_repo_markdown_bundle",
    "main",
    "namespace_from_operation",
    "perform_command",
    "restore_repo_snapshot",
    "sync_repo_toc_from_local_dir",
]


if __name__ == "__main__":
    raise SystemExit(main())

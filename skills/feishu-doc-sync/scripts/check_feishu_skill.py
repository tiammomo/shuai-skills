#!/usr/bin/env python3
"""Local smoke checks for the feishu-doc-sync scaffold."""

from __future__ import annotations

import argparse
import hashlib
import base64
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse
import zlib

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "feishu_doc_sync.py"


def default_validator_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    return codex_home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"


def resolve_validator_path(raw_path: str) -> Path:
    return Path(raw_path).expanduser().resolve()


def run_step(label: str, command: List[str]) -> None:
    print(f"==> {label}")
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n", file=sys.stderr)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def run_cli(*args: str, env: Optional[Dict[str, str]] = None) -> str:
    process = subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(args)}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )
    return process.stdout.strip()


def get_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def extract_json_object(text: str) -> dict:
    start = text.find("{")
    if start == -1:
        raise RuntimeError(f"No JSON object found in output:\n{text}")
    return json.loads(text[start:])


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def encode_text_snapshot(text: str) -> dict:
    raw_bytes = text.encode("utf-8")
    return {
        "encoding": "zlib+base64:utf-8",
        "data": base64.b64encode(zlib.compress(raw_bytes, level=9)).decode("ascii"),
        "length": len(raw_bytes),
        "content_hash": sha256_text(text),
    }


def make_text_elements(text: str) -> list[dict]:
    return [
        {
            "text_run": {
                "content": text,
                "text_element_style": {},
            }
        }
    ]


def make_mock_document_blocks(document_id: str, title: str, paragraphs: list[str]) -> list[dict]:
    children: list[str] = []
    blocks: list[dict] = [
        {
            "block_id": document_id,
            "block_type": 1,
            "children": children,
            "page": {
                "elements": make_text_elements(title),
            },
        }
    ]
    for index, paragraph in enumerate(paragraphs, start=1):
        block_id = f"blk-{document_id}-{index}"
        children.append(block_id)
        blocks.append(
            {
                "block_id": block_id,
                "block_type": 2,
                "parent_id": document_id,
                "children": [],
                "text": {
                    "elements": make_text_elements(paragraph),
                },
            }
        )
    return blocks


class MockFeishuHandler(BaseHTTPRequestHandler):
    documents = {
        "dox-mock": {
            "title": "Mock Document",
            "revision_id": 1,
            "children": ["blk-heading", "blk-paragraph"],
            "url": "https://example.test/docx/dox-mock",
            "raw_content": "Mock Document\nHello from raw content.\n",
        },
        "dox-root-a": {
            "title": "Mock Root Doc A",
            "revision_id": 3,
            "children": [
                "blk-root-a-heading",
                "blk-root-a-paragraph",
                "blk-root-a-bullet",
                "blk-root-a-ordered",
                "blk-root-a-quote",
                "blk-root-a-code",
                "blk-root-a-callout",
                "blk-root-a-table",
                "blk-root-a-image",
                "blk-root-a-file",
            ],
            "url": "https://example.test/docx/dox-root-a",
            "raw_content": "Mock Root Doc A\nRoot A content.\n",
            "blocks": [
                {
                    "block_id": "dox-root-a",
                    "block_type": 1,
                    "children": [
                        "blk-root-a-heading",
                        "blk-root-a-paragraph",
                        "blk-root-a-bullet",
                        "blk-root-a-ordered",
                        "blk-root-a-quote",
                        "blk-root-a-code",
                        "blk-root-a-callout",
                        "blk-root-a-table",
                        "blk-root-a-image",
                        "blk-root-a-file",
                    ],
                    "page": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": "Mock Root Doc A",
                                    "text_element_style": {},
                                }
                            }
                        ]
                    },
                },
                {
                    "block_id": "blk-root-a-heading",
                    "block_type": 4,
                    "parent_id": "dox-root-a",
                    "children": [],
                    "heading2": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": "Architecture",
                                    "text_element_style": {},
                                }
                            }
                        ]
                    },
                },
                {
                    "block_id": "blk-root-a-paragraph",
                    "block_type": 2,
                    "parent_id": "dox-root-a",
                    "children": [],
                    "text": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": "High fidelity ",
                                    "text_element_style": {},
                                }
                            },
                            {
                                "text_run": {
                                    "content": "paragraph",
                                    "text_element_style": {"bold": True},
                                }
                            },
                            {
                                "text_run": {
                                    "content": " from blocks.",
                                    "text_element_style": {},
                                }
                            },
                        ]
                    },
                },
                {
                    "block_id": "blk-root-a-bullet",
                    "block_type": 12,
                    "parent_id": "dox-root-a",
                    "children": [],
                    "bullet": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": "First bullet",
                                    "text_element_style": {},
                                }
                            }
                        ]
                    },
                },
                {
                    "block_id": "blk-root-a-ordered",
                    "block_type": 13,
                    "parent_id": "dox-root-a",
                    "children": [],
                    "ordered": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": "First ordered step",
                                    "text_element_style": {},
                                }
                            }
                        ]
                    },
                },
                {
                    "block_id": "blk-root-a-quote",
                    "block_type": 14,
                    "parent_id": "dox-root-a",
                    "children": [],
                    "quote": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": "Important note from the block tree.",
                                    "text_element_style": {},
                                }
                            }
                        ]
                    },
                },
                {
                    "block_id": "blk-root-a-code",
                    "block_type": 15,
                    "parent_id": "dox-root-a",
                    "children": [],
                    "code": {
                        "language": "bash",
                        "content": "echo \"smoke\"\npython -m py_compile",
                    },
                },
                {
                    "block_id": "blk-root-a-callout",
                    "block_type": 19,
                    "parent_id": "dox-root-a",
                    "children": ["blk-root-a-callout-text"],
                    "callout": {
                        "background_color": 4,
                    },
                },
                {
                    "block_id": "blk-root-a-callout-text",
                    "block_type": 2,
                    "parent_id": "blk-root-a-callout",
                    "children": [],
                    "text": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": "Review this callout.",
                                    "text_element_style": {},
                                }
                            }
                        ]
                    },
                },
                {
                    "block_id": "blk-root-a-table",
                    "block_type": 31,
                    "parent_id": "dox-root-a",
                    "children": ["blk-root-a-cell-1", "blk-root-a-cell-2"],
                    "table": {
                        "cells": ["blk-root-a-cell-1", "blk-root-a-cell-2"],
                        "property": {
                            "row_size": 1,
                            "column_size": 2,
                        },
                    },
                },
                {
                    "block_id": "blk-root-a-cell-1",
                    "block_type": 32,
                    "parent_id": "blk-root-a-table",
                    "children": ["blk-root-a-cell-1-text"],
                    "table_cell": {},
                },
                {
                    "block_id": "blk-root-a-cell-1-text",
                    "block_type": 2,
                    "parent_id": "blk-root-a-cell-1",
                    "children": [],
                    "text": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": "Column A",
                                    "text_element_style": {},
                                }
                            }
                        ]
                    },
                },
                {
                    "block_id": "blk-root-a-cell-2",
                    "block_type": 32,
                    "parent_id": "blk-root-a-table",
                    "children": ["blk-root-a-cell-2-text"],
                    "table_cell": {},
                },
                {
                    "block_id": "blk-root-a-cell-2-text",
                    "block_type": 2,
                    "parent_id": "blk-root-a-cell-2",
                    "children": [],
                    "text": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": "Column B",
                                    "text_element_style": {},
                                }
                            }
                        ]
                    },
                },
                {
                    "block_id": "blk-root-a-image",
                    "block_type": 27,
                    "parent_id": "dox-root-a",
                    "children": [],
                    "image": {
                        "token": "box-root-a-image",
                        "caption": {
                            "content": "Architecture diagram",
                        },
                    },
                },
                {
                    "block_id": "blk-root-a-file",
                    "block_type": 23,
                    "parent_id": "dox-root-a",
                    "children": [],
                    "file": {
                        "token": "box-root-a-file",
                        "name": "Architecture.pdf",
                        "view_type": 1,
                    },
                },
            ],
        },
        "dox-root-b": {
            "title": "Mock Root Doc B",
            "revision_id": 4,
            "children": [],
            "url": "https://example.test/docx/dox-root-b",
            "raw_content": "Mock Root Doc B\nRoot B content.\n",
        },
        "dox-team-note": {
            "title": "Team Note",
            "revision_id": 2,
            "children": [],
            "url": "https://example.test/docx/dox-team-note",
            "raw_content": "Team Note\nNested team note content.\n",
        },
        "dox-archive-note": {
            "title": "Archive Note",
            "revision_id": 1,
            "children": [],
            "url": "https://example.test/docx/dox-archive-note",
            "raw_content": "Archive Note\nArchived nested content.\n",
        }
    }
    drive_files = {
        "fld-root-mock": [
            {
                "name": "Mock Root Doc A",
                "type": "docx",
                "token": "dox-root-a",
                "parent_token": "fld-root-mock",
                "url": "https://example.test/docx/dox-root-a",
                "created_time": "1773500000",
                "modified_time": "1773500001",
            },
            {
                "name": "Mock Root Doc B",
                "type": "docx",
                "token": "dox-root-b",
                "parent_token": "fld-root-mock",
                "url": "https://example.test/docx/dox-root-b",
                "created_time": "1773500002",
                "modified_time": "1773500003",
            },
            {
                "name": "Team Notes",
                "type": "folder",
                "token": "fld-team-notes",
                "parent_token": "fld-root-mock",
                "url": "https://example.test/folder/fld-team-notes",
                "created_time": "1773500004",
                "modified_time": "1773500005",
            },
        ],
        "fld-team-notes": [
            {
                "name": "Team Note",
                "type": "docx",
                "token": "dox-team-note",
                "parent_token": "fld-team-notes",
                "url": "https://example.test/docx/dox-team-note",
                "created_time": "1773500006",
                "modified_time": "1773500007",
            },
            {
                "name": "Archive",
                "type": "folder",
                "token": "fld-archive",
                "parent_token": "fld-team-notes",
                "url": "https://example.test/folder/fld-archive",
                "created_time": "1773500008",
                "modified_time": "1773500009",
            },
        ],
        "fld-archive": [
            {
                "name": "Archive Note",
                "type": "docx",
                "token": "dox-archive-note",
                "parent_token": "fld-archive",
                "url": "https://example.test/docx/dox-archive-note",
                "created_time": "1773500010",
                "modified_time": "1773500011",
            }
        ],
    }
    create_counter = 0
    folder_counter = 0
    media_counter = 0
    media_uploads = []
    descendant_requests = []

    @classmethod
    def _ensure_folder_bucket(cls, folder_token: str) -> list[dict]:
        return cls.drive_files.setdefault(folder_token, [])

    @classmethod
    def _register_drive_child(cls, parent_token: str, entry: dict) -> None:
        bucket = cls._ensure_folder_bucket(parent_token)
        token = str(entry.get("token") or "")
        for index, existing in enumerate(bucket):
            if str(existing.get("token") or "") == token:
                bucket[index] = entry
                return
        bucket.append(entry)

    @classmethod
    def _remove_drive_child(cls, file_token: str) -> None:
        for parent_token, bucket in cls.drive_files.items():
            cls.drive_files[parent_token] = [
                item for item in bucket if str(item.get("token") or "") != file_token
            ]

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> dict:
        raw_bytes = self._read_raw_body()
        if not raw_bytes:
            return {}
        raw = raw_bytes.decode("utf-8", "replace")
        if not raw:
            return {}
        return json.loads(raw)

    def _read_raw_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _parse_multipart_form_data(self) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
        content_type = self.headers.get("Content-Type", "")
        boundary_match = re.search(r'boundary="?([^";]+)"?', content_type)
        if not boundary_match:
            return {}, {}
        boundary = boundary_match.group(1).encode("utf-8")
        raw_body = self._read_raw_body()
        fields: dict[str, str] = {}
        files: dict[str, dict[str, object]] = {}
        delimiter = b"--" + boundary
        for part in raw_body.split(delimiter):
            stripped = part.strip()
            if not stripped or stripped == b"--":
                continue
            if stripped.endswith(b"--"):
                stripped = stripped[:-2]
            if stripped.startswith(b"\r\n"):
                stripped = stripped[2:]
            if b"\r\n\r\n" not in stripped:
                continue
            raw_headers, content = stripped.split(b"\r\n\r\n", 1)
            content = content.rstrip(b"\r\n")
            header_lines = raw_headers.decode("utf-8", "replace").split("\r\n")
            disposition = next(
                (line for line in header_lines if line.lower().startswith("content-disposition:")),
                "",
            )
            name_match = re.search(r'name="([^"]+)"', disposition)
            if not name_match:
                continue
            field_name = name_match.group(1)
            filename_match = re.search(r'filename="([^"]*)"', disposition)
            part_content_type = ""
            for line in header_lines:
                if line.lower().startswith("content-type:"):
                    part_content_type = line.split(":", 1)[1].strip()
                    break
            if filename_match:
                files[field_name] = {
                    "filename": filename_match.group(1),
                    "content_type": part_content_type,
                    "content": content,
                    "size": len(content),
                }
                continue
            fields[field_name] = content.decode("utf-8", "replace")
        return fields, files

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if self.path == "/open-apis/auth/v3/app_access_token/internal":
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "app_access_token": "a-mock-app-token-from-app-access-token-endpoint",
                    "expire": 7200,
                },
            )
            return

        if self.path == "/open-apis/auth/v3/tenant_access_token/internal":
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "tenant_access_token": "t-mock-tenant-token-1234567890",
                    "app_access_token": "a-mock-app-token-0987654321",
                    "expire": 7200,
                },
            )
            return

        if parsed.path == "/open-apis/docx/v1/documents":
            payload = self._read_json_body()
            MockFeishuHandler.create_counter += 1
            document_id = f"dox-created-{MockFeishuHandler.create_counter}"
            title = payload.get("title") or f"Created Mock Document {MockFeishuHandler.create_counter}"
            folder_token = str(payload.get("folder_token") or "")
            MockFeishuHandler.documents[document_id] = {
                "title": title,
                "revision_id": 1,
                "children": [],
                "url": f"https://example.test/docx/{document_id}",
                "raw_content": f"{title}\n",
            }
            if folder_token:
                MockFeishuHandler._register_drive_child(
                    folder_token,
                    {
                        "name": title,
                        "type": "docx",
                        "token": document_id,
                        "parent_token": folder_token,
                        "url": f"https://example.test/docx/{document_id}",
                        "created_time": "1773500100",
                        "modified_time": "1773500101",
                    },
                )
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "document": {
                            "document_id": document_id,
                            "title": title,
                            "revision_id": 1,
                            "url": f"https://example.test/docx/{document_id}",
                        }
                    },
                },
            )
            return

        if parsed.path == "/open-apis/drive/v1/files/create_folder":
            payload = self._read_json_body()
            parent_token = str(payload.get("folder_token") or "")
            name = str(payload.get("name") or "").strip() or "New Folder"
            MockFeishuHandler.folder_counter += 1
            folder_token = f"fld-created-{MockFeishuHandler.folder_counter}"
            folder_url = f"https://example.test/folder/{folder_token}"
            MockFeishuHandler._ensure_folder_bucket(folder_token)
            if parent_token:
                MockFeishuHandler._register_drive_child(
                    parent_token,
                    {
                        "name": name,
                        "type": "folder",
                        "token": folder_token,
                        "parent_token": parent_token,
                        "url": folder_url,
                        "created_time": "1773500102",
                        "modified_time": "1773500103",
                    },
                )
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "folder": {
                            "token": folder_token,
                            "parent_token": parent_token,
                            "name": name,
                            "type": "folder",
                            "url": folder_url,
                        }
                    },
                },
            )
            return

        if parsed.path == "/open-apis/drive/v1/medias/upload_all":
            fields, files = self._parse_multipart_form_data()
            MockFeishuHandler.media_counter += 1
            file_token = f"box-mock-{MockFeishuHandler.media_counter}"
            file_info = files.get("file", {})
            MockFeishuHandler.media_uploads.append(
                {
                    "file_token": file_token,
                    "document_id": fields.get("parent_node"),
                    "parent_type": fields.get("parent_type"),
                    "file_name": fields.get("file_name"),
                    "size": fields.get("size"),
                    "checksum": fields.get("checksum"),
                    "extra": fields.get("extra"),
                    "content_type": file_info.get("content_type"),
                    "uploaded_size": file_info.get("size"),
                }
            )
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "file_token": file_token,
                    },
                },
            )
            return

        if parsed.path == "/open-apis/docx/v1/documents/blocks/convert":
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "first_level_block_ids": [
                            "tmp-heading",
                            "tmp-paragraph",
                        ],
                        "blocks": [
                            {
                                "block_id": "tmp-heading",
                                "parent_id": "",
                                "children": [],
                                "block_type": 3,
                                "heading1": {
                                    "elements": [
                                        {
                                            "text_run": {
                                                "content": "Mock Title",
                                                "text_element_style": {
                                                    "bold": False,
                                                    "inline_code": False,
                                                    "italic": False,
                                                    "strikethrough": False,
                                                    "underline": False,
                                                },
                                            }
                                        }
                                    ],
                                    "style": {"align": 1, "folded": False},
                                },
                            },
                            {
                                "block_id": "tmp-paragraph",
                                "parent_id": "",
                                "children": [],
                                "block_type": 2,
                                "text": {
                                    "elements": [
                                        {
                                            "text_run": {
                                                "content": "Mock paragraph",
                                                "text_element_style": {
                                                    "bold": False,
                                                    "inline_code": False,
                                                    "italic": False,
                                                    "strikethrough": False,
                                                    "underline": False,
                                                },
                                            }
                                        }
                                    ],
                                    "style": {"align": 1, "folded": False},
                                },
                            },
                        ],
                        "block_id_to_image_urls": {},
                    },
                },
            )
            return

        if (
            parsed.path.startswith("/open-apis/docx/v1/documents/")
            and parsed.path.endswith("/descendant")
        ):
            parts = parsed.path.strip("/").split("/")
            document_id = parts[4]
            payload = self._read_json_body()
            MockFeishuHandler.descendant_requests.append(
                {
                    "document_id": document_id,
                    "payload": payload,
                }
            )
            temp_children = payload.get("children_id", [])
            if not isinstance(temp_children, list):
                temp_children = []
            document = MockFeishuHandler.documents.setdefault(
                document_id,
                {
                    "title": f"Mock {document_id}",
                    "revision_id": 1,
                    "children": [],
                    "url": f"https://example.test/docx/{document_id}",
                },
            )
            document["revision_id"] = int(document.get("revision_id", 1)) + 1
            created_children = []
            relations = []
            for temp_id in temp_children:
                temp_id_value = str(temp_id)
                block_id = f"blk-{document_id}-{temp_id_value}"
                relations.append({"temporary_block_id": temp_id_value, "block_id": block_id})
                created_children.append({"block_id": block_id, "block_type": 2, "parent_id": document_id})
            document["children"] = [child["block_id"] for child in created_children]
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "document_revision_id": document["revision_id"],
                        "client_token": "mock-client-token",
                        "block_id_relations": relations,
                        "children": created_children,
                    },
                },
            )
            return

        if self.path == "/open-apis/authen/v2/oauth/token":
            self._write_json(
                200,
                {
                    "access_token": "u-mock-user-access-token-1234567890",
                    "refresh_token": "r-mock-refresh-token-0987654321",
                    "expires_in": 7200,
                    "token_type": "Bearer",
                    "name": "Mock User",
                    "open_id": "ou_mock_user_access",
                },
            )
            return

        self._write_json(404, {"code": 404, "msg": "not found"})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path.startswith("/open-apis/docx/v1/documents/") and parsed.path.endswith("/raw_content"):
            document_id = parsed.path.strip("/").split("/")[4]
            document = MockFeishuHandler.documents.get(document_id, {})
            title = document.get("title", "Mock Document")
            raw_content = document.get("raw_content", f"{title}\nHello from raw content.\n")
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "content": raw_content,
                    },
                },
            )
            return

        if parsed.path.startswith("/open-apis/docx/v1/documents/") and parsed.path.endswith("/blocks"):
            document_id = parsed.path.strip("/").split("/")[4]
            document = MockFeishuHandler.documents.get(document_id)
            if document is None:
                self._write_json(404, {"code": 404, "msg": "not found"})
                return
            block_items = document.get("blocks")
            if not isinstance(block_items, list):
                block_items = [
                    {
                        "block_id": document_id,
                        "block_type": 1,
                        "children": list(document.get("children", [])),
                    }
                ]
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "items": block_items,
                        "has_more": False,
                        "page_token": "",
                    },
                },
            )
            return

        if parsed.path.startswith("/open-apis/docx/v1/documents/"):
            document_id = parsed.path.strip("/").split("/")[4]
            document = MockFeishuHandler.documents.get(document_id)
            if document is None:
                self._write_json(404, {"code": 404, "msg": "not found"})
                return
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "document": {
                            "document_id": document_id,
                            "title": document["title"],
                            "revision_id": document["revision_id"],
                        }
                    },
                },
            )
            return

        if parsed.path == "/open-apis/drive/explorer/v2/root_folder/meta":
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "id": "7617000000000000000",
                        "token": "fld-root-mock",
                        "user_id": "ou_mock_user",
                    },
                },
            )
            return

        if parsed.path == "/open-apis/drive/v1/files":
            query = parse_qs(parsed.query)
            folder_token = (query.get("folder_token") or [""])[0]
            if folder_token in MockFeishuHandler.drive_files:
                self._write_json(
                    200,
                    {
                        "code": 0,
                        "msg": "ok",
                        "data": {
                            "has_more": False,
                            "next_page_token": None,
                            "files": MockFeishuHandler.drive_files[folder_token],
                        },
                    },
                )
                return

        self._write_json(404, {"code": 404, "msg": "not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if (
            parsed.path.startswith("/open-apis/docx/v1/documents/")
            and parsed.path.endswith("/children/batch_delete")
        ):
            parts = parsed.path.strip("/").split("/")
            document_id = parts[4]
            block_id = parts[6]
            payload = self._read_json_body()
            start_index = int(payload.get("start_index", 0))
            end_index = int(payload.get("end_index", 0))
            document = MockFeishuHandler.documents.setdefault(
                document_id,
                {
                    "title": f"Mock {document_id}",
                    "revision_id": 1,
                    "children": [],
                    "url": f"https://example.test/docx/{document_id}",
                },
            )
            children = list(document.get("children", []))
            if block_id == document_id:
                document["children"] = children[:start_index] + children[end_index:]
            document["revision_id"] = int(document.get("revision_id", 1)) + 1
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "document_revision_id": document["revision_id"],
                        "client_token": (query.get("client_token") or ["mock-client-token"])[0],
                    },
                },
            )
            return

        if parsed.path.startswith("/open-apis/drive/v1/files/") and (query.get("type") or [""])[0] == "docx":
            file_token = parsed.path.rsplit("/", 1)[-1]
            MockFeishuHandler.documents.pop(file_token, None)
            MockFeishuHandler._remove_drive_child(file_token)
            self._write_json(200, {"code": 0, "msg": "ok", "data": {}})
            return

        self._write_json(404, {"code": 404, "msg": "not found"})


def start_mock_server() -> Tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockFeishuHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def run_selftest() -> None:
    doctor = json.loads(run_cli("doctor"))
    if "required_env" not in doctor.get("result", {}):
        raise RuntimeError("doctor output is missing required_env")

    server, base_url = start_mock_server()
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            sample = Path(tmp_dir) / "sample.md"
            sample.write_text(
                "---\n"
                "title: Sample Doc\n"
                "feishu_doc_token: dox1234567890abcdefghijklmn\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# Sample Doc\n"
                "\n"
                "Hello from the scaffold.\n",
                encoding="utf-8",
            )

            push_plan = json.loads(run_cli("plan-push", str(sample)))
            if push_plan.get("result", {}).get("action") != "update_doc":
                raise RuntimeError(f"Unexpected push action: {push_plan}")

            pull_plan = json.loads(run_cli("plan-pull", str(sample)))
            if pull_plan.get("result", {}).get("action") != "pull_doc":
                raise RuntimeError(f"Unexpected pull action: {pull_plan}")

            token_result = json.loads(
                run_cli(
                    "tenant-token",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not token_result.get("ok"):
                raise RuntimeError(f"Unexpected tenant-token result: {token_result}")

            user_auth_result = json.loads(
                run_cli(
                    "user-auth-url",
                    "--app-id",
                    "cli_mock",
                    "--base-url",
                    base_url,
                    "--redirect-uri",
                    "https://example.test/callback",
                    "--state",
                    "state123",
                )
            )
            authorization_url = user_auth_result.get("result", {}).get("authorization_url")
            if not user_auth_result.get("ok") or not authorization_url:
                raise RuntimeError(f"Unexpected user-auth-url result: {user_auth_result}")
            if "state123" not in authorization_url:
                raise RuntimeError(f"user-auth-url did not preserve state: {user_auth_result}")

            validate_result = json.loads(
                run_cli(
                    "validate-tenant",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--document-id",
                    "dox-mock",
                )
            )
            if not validate_result.get("ok"):
                raise RuntimeError(f"Unexpected validate-tenant result: {validate_result}")

            user_env = os.environ.copy()
            user_env["FEISHU_USER_ACCESS_TOKEN"] = "u-mock-user-access-token-1234567890"
            user_env.pop("FEISHU_APP_ID", None)
            user_env.pop("FEISHU_APP_SECRET", None)
            user_env.pop("FEISHU_TENANT_ACCESS_TOKEN", None)

            validate_user_result = json.loads(
                run_cli(
                    "validate-user",
                    "--base-url",
                    base_url,
                    "--document-id",
                    "dox-mock",
                    env=user_env,
                )
            )
            if not validate_user_result.get("ok") or validate_user_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected validate-user result: {validate_user_result}")

            create_result = json.loads(
                run_cli(
                    "create-document",
                    "Connectivity Check",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not create_result.get("ok"):
                raise RuntimeError(f"Unexpected create-document result: {create_result}")

            append_result = json.loads(
                run_cli(
                    "append-markdown",
                    "dox-mock",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--content",
                    "# Mock Title\n\nMock paragraph\n",
                )
            )
            if not append_result.get("ok"):
                raise RuntimeError(f"Unexpected append-markdown result: {append_result}")
            if append_result.get("result", {}).get("write_result", {}).get("child_count") != 2:
                raise RuntimeError(f"Unexpected append-markdown child count: {append_result}")

            with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8-sig") as handle:
                handle.write("---\ntitle: Mock Front Matter\n---\n# Mock Title\n\nMock paragraph\n")
                bom_markdown_path = Path(handle.name)
            try:
                append_file_result = json.loads(
                    run_cli(
                        "append-markdown",
                        "dox-mock",
                        "--app-id",
                        "cli_mock",
                        "--app-secret",
                        "mock_secret",
                        "--base-url",
                        base_url,
                        "--markdown-file",
                        str(bom_markdown_path),
                    )
                )
            finally:
                bom_markdown_path.unlink(missing_ok=True)
            if not append_file_result.get("ok"):
                raise RuntimeError(f"Unexpected append-markdown file result: {append_file_result}")
            source_info = append_file_result.get("result", {}).get("source", {})
            if source_info.get("has_front_matter") is not True:
                raise RuntimeError(f"Expected front matter detection for file append: {append_file_result}")
            if source_info.get("front_matter_keys") != ["title"]:
                raise RuntimeError(f"Unexpected front matter keys for file append: {append_file_result}")

            replace_result = json.loads(
                run_cli(
                    "replace-markdown",
                    "dox-mock",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--confirm-replace",
                    "--content",
                    "# Mock Title\n\nMock paragraph\n",
                )
            )
            if not replace_result.get("ok"):
                raise RuntimeError(f"Unexpected replace-markdown result: {replace_result}")
            replace_payload = replace_result.get("result", {})
            if replace_payload.get("delete", {}).get("deleted_count") != 2:
                raise RuntimeError(f"Unexpected replace-markdown delete result: {replace_result}")
            if replace_payload.get("append", {}).get("write_result", {}).get("child_count") != 2:
                raise RuntimeError(f"Unexpected replace-markdown append result: {replace_result}")

            user_append_result = json.loads(
                run_cli(
                    "append-markdown",
                    "dox-mock",
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--confirm-user-write",
                    "--content",
                    "User mode append paragraph.\n",
                    env=user_env,
                )
            )
            if not user_append_result.get("ok") or user_append_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode append-markdown result: {user_append_result}")

            blocked_user_replace = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "replace-markdown",
                    "dox-mock",
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--confirm-replace",
                    "--content",
                    "# User Replace\n\nBlocked until confirmed.\n",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=user_env,
            )
            if blocked_user_replace.returncode == 0:
                raise RuntimeError(f"user-mode replace-markdown should require --confirm-user-write: {blocked_user_replace.stdout}")
            blocked_user_replace_payload = extract_json_object(blocked_user_replace.stdout)
            if "--confirm-user-write" not in str(blocked_user_replace_payload.get("error") or ""):
                raise RuntimeError(f"user-mode replace-markdown did not explain the protection failure: {blocked_user_replace_payload}")

            user_replace_result = json.loads(
                run_cli(
                    "replace-markdown",
                    "dox-mock",
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--confirm-replace",
                    "--confirm-user-write",
                    "--content",
                    "# User Replace\n\nConfirmed replace.\n",
                    env=user_env,
                )
            )
            if not user_replace_result.get("ok") or user_replace_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode replace-markdown result: {user_replace_result}")
            user_replace_payload = user_replace_result.get("result", {})
            if user_replace_payload.get("delete", {}).get("ok") is not True:
                raise RuntimeError(f"user-mode replace-markdown did not delete the previous root children: {user_replace_result}")

            push_file_root = Path(tmp_dir) / "push-file"
            push_file_root.mkdir(parents=True, exist_ok=True)
            push_file = push_file_root / "create.md"
            push_file.write_text(
                "---\n"
                "title: Push File Doc\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# Push File Doc\n"
                "\n"
                "Created by push-markdown.\n",
                encoding="utf-8",
            )
            push_file_result = json.loads(
                run_cli(
                    "push-markdown",
                    str(push_file),
                    "--root",
                    str(push_file_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not push_file_result.get("ok"):
                raise RuntimeError(f"Unexpected push-markdown result: {push_file_result}")
            push_file_index = push_file_root / "feishu-index.json"
            if not push_file_index.is_file():
                raise RuntimeError("push-markdown did not create feishu-index.json")
            push_file_index_payload = json.loads(push_file_index.read_text(encoding="utf-8"))
            if len(push_file_index_payload.get("files", [])) != 1:
                raise RuntimeError(f"Unexpected push-markdown index payload: {push_file_index_payload}")
            if not push_file_index_payload["files"][0].get("doc_token"):
                raise RuntimeError(f"push-markdown index entry is missing doc_token: {push_file_index_payload}")
            if not push_file_index_payload["files"][0].get("body_hash") or not push_file_index_payload["files"][0].get("remote_revision_id"):
                raise RuntimeError(f"push-markdown index entry is missing sync baseline fields: {push_file_index_payload}")

            user_push_root = Path(tmp_dir) / "push-file-user"
            user_push_root.mkdir(parents=True, exist_ok=True)
            user_push_file = user_push_root / "mapped.md"
            user_push_file.write_text(
                "---\n"
                "title: User Push Doc\n"
                "feishu_doc_token: dox-mock\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# User Push Doc\n"
                "\n"
                "Updated by user push-markdown.\n",
                encoding="utf-8",
            )
            user_push_result = json.loads(
                run_cli(
                    "push-markdown",
                    str(user_push_file),
                    "--root",
                    str(user_push_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--confirm-user-write",
                    "--confirm-replace",
                    env=user_env,
                )
            )
            if not user_push_result.get("ok") or user_push_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode push-markdown result: {user_push_result}")
            user_push_index = user_push_root / "feishu-index.user.json"
            if not user_push_index.is_file() or (user_push_root / "feishu-index.json").exists():
                raise RuntimeError("user-mode push-markdown should write to feishu-index.user.json and keep the generic tenant index untouched by default")
            user_push_index_payload = json.loads(user_push_index.read_text(encoding="utf-8"))
            user_push_entry = user_push_index_payload.get("files", [{}])[0]
            if user_push_entry.get("doc_token") != "dox-mock":
                raise RuntimeError(f"user-mode push-markdown did not persist the mapped doc token: {user_push_index_payload}")
            if user_push_index_payload.get("auth_mode") != "user" or user_push_entry.get("auth_mode") != "user":
                raise RuntimeError(f"user-mode push-markdown did not persist user-mode scope metadata: {user_push_index_payload}")

            blocked_user_create_file = user_push_root / "blocked-create.md"
            blocked_user_create_file.write_text("# Blocked Create\n\nNo remote mapping yet.\n", encoding="utf-8")
            blocked_user_create = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "push-markdown",
                    str(blocked_user_create_file),
                    "--root",
                    str(user_push_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--confirm-user-write",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=user_env,
            )
            if blocked_user_create.returncode == 0:
                raise RuntimeError(f"user-mode push-markdown should block create flow by default: {blocked_user_create.stdout}")
            blocked_user_create_payload = extract_json_object(blocked_user_create.stdout)
            if "--allow-user-create" not in str(blocked_user_create_payload.get("error") or ""):
                raise RuntimeError(f"user-mode push-markdown did not explain the protected create guardrail: {blocked_user_create_payload}")

            user_create_file = user_push_root / "allowed-create.md"
            user_create_file.write_text(
                "---\n"
                "title: User Created Doc\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# User Created Doc\n"
                "\n"
                "Created through protected user push.\n",
                encoding="utf-8",
            )
            user_create_result = json.loads(
                run_cli(
                    "push-markdown",
                    str(user_create_file),
                    "--root",
                    str(user_push_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--confirm-user-write",
                    "--allow-user-create",
                    env=user_env,
                )
            )
            if not user_create_result.get("ok") or user_create_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode create push-markdown result: {user_create_result}")
            created_doc_token = user_create_result.get("result", {}).get("index_entry", {}).get("doc_token")
            if not str(created_doc_token or "").startswith("dox-created-"):
                raise RuntimeError(f"user-mode push-markdown create flow did not persist a created doc token: {user_create_result}")

            push_dir_root = Path(tmp_dir) / "push-dir"
            push_dir_root.mkdir(parents=True, exist_ok=True)
            (push_dir_root / "alpha.md").write_text(
                "# Alpha\n\nHello alpha.\n",
                encoding="utf-8",
            )
            (push_dir_root / "beta.md").write_text(
                "---\n"
                "title: Beta File\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# Beta\n\nHello beta.\n",
                encoding="utf-8",
            )
            push_dir_result = json.loads(
                run_cli(
                    "push-dir",
                    str(push_dir_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not push_dir_result.get("ok"):
                raise RuntimeError(f"Unexpected push-dir result: {push_dir_result}")
            if push_dir_result.get("result", {}).get("pushed_count") != 2:
                raise RuntimeError(f"Unexpected push-dir pushed_count: {push_dir_result}")
            push_dir_index = push_dir_root / "feishu-index.json"
            if not push_dir_index.is_file():
                raise RuntimeError("push-dir did not create feishu-index.json")
            push_dir_index_payload = json.loads(push_dir_index.read_text(encoding="utf-8"))
            if len(push_dir_index_payload.get("files", [])) != 2:
                raise RuntimeError(f"Unexpected push-dir index payload: {push_dir_index_payload}")

            mirror_push_dir_root = Path(tmp_dir) / "push-dir-mirror"
            (mirror_push_dir_root / "Guides" / "API").mkdir(parents=True, exist_ok=True)
            (mirror_push_dir_root / "Guides" / "API" / "intro.md").write_text(
                "---\n"
                "title: Intro Guide\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# Intro Guide\n\nMirror this nested file.\n",
                encoding="utf-8",
            )
            mirror_push_dir_result = json.loads(
                run_cli(
                    "push-dir",
                    str(mirror_push_dir_root),
                    "--folder-token",
                    "fld-root-mock",
                    "--mirror-remote-folders",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not mirror_push_dir_result.get("ok"):
                raise RuntimeError(f"Unexpected mirrored push-dir result: {mirror_push_dir_result}")
            mirror_result_payload = mirror_push_dir_result.get("result", {})
            if mirror_result_payload.get("pushed_count") != 1:
                raise RuntimeError(f"Unexpected mirrored push-dir pushed_count: {mirror_push_dir_result}")
            mirrored_file_result = mirror_result_payload.get("results", [{}])[0]
            folder_resolution = mirrored_file_result.get("folder_resolution", {})
            if len(folder_resolution.get("created", [])) != 2:
                raise RuntimeError(f"Expected two created remote folders for mirrored push-dir: {mirror_push_dir_result}")
            mirror_push_index = mirror_push_dir_root / "feishu-index.json"
            mirror_push_index_payload = json.loads(mirror_push_index.read_text(encoding="utf-8"))
            mirrored_entry = next(
                (
                    entry
                    for entry in mirror_push_index_payload.get("files", [])
                    if entry.get("relative_path") == "Guides/API/intro.md"
                ),
                None,
            )
            if not mirrored_entry or not str(mirrored_entry.get("folder_token") or "").startswith("fld-created-"):
                raise RuntimeError(f"Mirrored push-dir did not persist the derived folder token: {mirror_push_index_payload}")

            MockFeishuHandler.documents["dox-user-dir-mapped"] = {
                "title": "User Dir Mapped",
                "revision_id": 2,
                "children": [],
                "url": "https://example.test/docx/dox-user-dir-mapped",
                "raw_content": "User Dir Mapped\nRemote body before the user directory update.\n",
            }

            user_push_dir_root = Path(tmp_dir) / "user-push-dir"
            user_push_dir_root.mkdir(parents=True, exist_ok=True)
            (user_push_dir_root / "mapped.md").write_text(
                "---\n"
                "title: User Dir Mapped\n"
                "feishu_doc_token: dox-user-dir-mapped\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# User Dir Mapped\n\nUpdated from user dir.\n",
                encoding="utf-8",
            )
            blocked_user_push_dir = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "push-dir",
                    str(user_push_dir_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--confirm-replace",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=user_env,
            )
            if blocked_user_push_dir.returncode == 0:
                raise RuntimeError(f"user-mode push-dir should require --confirm-user-write: {blocked_user_push_dir.stdout}")
            blocked_user_push_dir_payload = extract_json_object(blocked_user_push_dir.stdout)
            if "--confirm-user-write" not in str(blocked_user_push_dir_payload.get("error") or ""):
                raise RuntimeError(f"user-mode push-dir did not explain the write protection failure: {blocked_user_push_dir_payload}")

            user_push_dir_result = json.loads(
                run_cli(
                    "push-dir",
                    str(user_push_dir_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--confirm-user-write",
                    "--confirm-replace",
                    env=user_env,
                )
            )
            if not user_push_dir_result.get("ok") or user_push_dir_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode push-dir mapped update result: {user_push_dir_result}")
            if user_push_dir_result.get("result", {}).get("pushed_count") != 1:
                raise RuntimeError(f"user-mode push-dir mapped update did not push one file: {user_push_dir_result}")
            user_push_dir_index = user_push_dir_root / "feishu-index.user.json"
            if not user_push_dir_index.is_file() or (user_push_dir_root / "feishu-index.json").exists():
                raise RuntimeError("user-mode push-dir should write to feishu-index.user.json by default")
            user_push_dir_index_payload = json.loads(user_push_dir_index.read_text(encoding="utf-8"))
            user_push_dir_entry = user_push_dir_index_payload.get("files", [{}])[0]
            if user_push_dir_entry.get("doc_token") != "dox-user-dir-mapped":
                raise RuntimeError(f"user-mode push-dir mapped update did not preserve the mapped doc token: {user_push_dir_index_payload}")
            if user_push_dir_entry.get("auth_mode") != "user" or user_push_dir_entry.get("visibility_scope") != "user_visible":
                raise RuntimeError(f"user-mode push-dir mapped update did not persist user scope metadata: {user_push_dir_index_payload}")

            blocked_user_create_dir_root = Path(tmp_dir) / "user-push-dir-blocked"
            (blocked_user_create_dir_root / "Guides" / "API").mkdir(parents=True, exist_ok=True)
            (blocked_user_create_dir_root / "Guides" / "API" / "intro.md").write_text(
                "---\n"
                "title: User Intro Guide\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# User Intro Guide\n\nShould stay blocked without explicit create opt-in.\n",
                encoding="utf-8",
            )
            created_folder_count_before = sum(1 for token in MockFeishuHandler.drive_files if str(token).startswith("fld-created-"))
            blocked_user_create_dir = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "push-dir",
                    str(blocked_user_create_dir_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--folder-token",
                    "fld-root-mock",
                    "--mirror-remote-folders",
                    "--confirm-user-write",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=user_env,
            )
            if blocked_user_create_dir.returncode == 0:
                raise RuntimeError(f"user-mode push-dir should block create flow by default: {blocked_user_create_dir.stdout}")
            blocked_user_create_dir_payload = extract_json_object(blocked_user_create_dir.stdout)
            if "--allow-user-create" not in str(blocked_user_create_dir_payload.get("result", {}).get("results", [{}])[0].get("error") or ""):
                raise RuntimeError(f"user-mode push-dir did not explain the protected create flow: {blocked_user_create_dir_payload}")
            created_folder_count_after = sum(1 for token in MockFeishuHandler.drive_files if str(token).startswith("fld-created-"))
            if created_folder_count_after != created_folder_count_before:
                raise RuntimeError("user-mode push-dir created remote folders before create flow was explicitly allowed")

            user_create_dir_root = Path(tmp_dir) / "user-push-dir-create"
            user_create_dir_root.mkdir(parents=True, exist_ok=True)
            (user_create_dir_root / "create.md").write_text(
                "---\n"
                "title: User Dir Create\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# User Dir Create\n\nCreate this doc through user-mode push-dir.\n",
                encoding="utf-8",
            )
            user_create_dir_result = json.loads(
                run_cli(
                    "push-dir",
                    str(user_create_dir_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--confirm-user-write",
                    "--allow-user-create",
                    env=user_env,
                )
            )
            if not user_create_dir_result.get("ok") or user_create_dir_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode push-dir create result: {user_create_dir_result}")
            user_create_dir_entry = user_create_dir_result.get("result", {}).get("results", [{}])[0].get("index_entry", {})
            if not str(user_create_dir_entry.get("doc_token") or "").startswith("dox-created-"):
                raise RuntimeError(f"user-mode push-dir create flow did not persist a created doc token: {user_create_dir_result}")

            get_result = json.loads(
                run_cli(
                    "get-document",
                    "dox-mock",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not get_result.get("ok"):
                raise RuntimeError(f"Unexpected get-document result: {get_result}")

            user_get_result = json.loads(
                run_cli(
                    "get-document",
                    "dox-mock",
                    "--auth-mode",
                    "user",
                    "--user-access-token",
                    "u-cli-user-access-token-1234567890",
                    "--base-url",
                    base_url,
                )
            )
            if not user_get_result.get("ok") or user_get_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode get-document result: {user_get_result}")

            raw_content_result = json.loads(
                run_cli(
                    "get-raw-content",
                    "dox-mock",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not raw_content_result.get("ok"):
                raise RuntimeError(f"Unexpected get-raw-content result: {raw_content_result}")
            raw_content = raw_content_result.get("result", {}).get("content", "")
            if "Hello from raw content." not in raw_content:
                raise RuntimeError(f"Unexpected raw content payload: {raw_content_result}")

            root_list_result = json.loads(
                run_cli(
                    "list-root-files",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not root_list_result.get("ok") or root_list_result.get("result", {}).get("file_count") != 4:
                raise RuntimeError(f"Unexpected list-root-files result: {root_list_result}")

            user_root_list_result = json.loads(
                run_cli(
                    "list-root-files",
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    env=user_env,
                )
            )
            if not user_root_list_result.get("ok") or user_root_list_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode list-root-files result: {user_root_list_result}")
            if user_root_list_result.get("result", {}).get("file_count") != 4:
                raise RuntimeError(f"Unexpected user-mode list-root-files count: {user_root_list_result}")

            folder_list_result = json.loads(
                run_cli(
                    "list-folder-files",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--recursive",
                )
            )
            if not folder_list_result.get("ok"):
                raise RuntimeError(f"Unexpected list-folder-files result: {folder_list_result}")
            folder_listing = folder_list_result.get("result", {})
            if folder_listing.get("file_count") != 5 or folder_listing.get("folder_count") != 4:
                raise RuntimeError(f"Unexpected recursive folder listing summary: {folder_list_result}")

            pull_root = Path(tmp_dir) / "pull-root"
            pull_markdown_result = json.loads(
                run_cli(
                    "pull-markdown",
                    "dox-root-a",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--root",
                    str(pull_root),
                    "--relative-path",
                    "imports/root-a.md",
                )
            )
            if not pull_markdown_result.get("ok"):
                raise RuntimeError(f"Unexpected pull-markdown result: {pull_markdown_result}")
            pulled_file = pull_root / "imports" / "root-a.md"
            if not pulled_file.is_file():
                raise RuntimeError("pull-markdown did not create the expected local Markdown file")
            pulled_text = pulled_file.read_text(encoding="utf-8")
            if "feishu_doc_token: dox-root-a" not in pulled_text or "Root A content." not in pulled_text:
                raise RuntimeError(f"Unexpected pull-markdown file content: {pulled_text}")
            pull_index = pull_root / "feishu-index.json"
            pull_index_payload = json.loads(pull_index.read_text(encoding="utf-8"))
            if pull_index_payload.get("files", [{}])[0].get("doc_token") != "dox-root-a":
                raise RuntimeError(f"Unexpected pull-markdown index payload: {pull_index_payload}")
            if pull_index_payload.get("files", [{}])[0].get("last_pull_fidelity") != "raw_content":
                raise RuntimeError(f"pull-markdown did not persist pull fidelity into the index: {pull_index_payload}")
            if pull_index_payload.get("files", [{}])[0].get("remote_revision_id") != 3:
                raise RuntimeError(f"pull-markdown did not persist the remote revision baseline: {pull_index_payload}")

            pull_markdown_high_root = Path(tmp_dir) / "pull-root-high"
            pull_markdown_high_result = json.loads(
                run_cli(
                    "pull-markdown",
                    "dox-root-a",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--root",
                    str(pull_markdown_high_root),
                    "--relative-path",
                    "imports/high-root-a.md",
                    "--fidelity",
                    "high",
                )
            )
            if not pull_markdown_high_result.get("ok"):
                raise RuntimeError(f"Unexpected high-fidelity pull-markdown result: {pull_markdown_high_result}")
            high_pull_payload = pull_markdown_high_result.get("result", {})
            if high_pull_payload.get("fidelity") != "high":
                raise RuntimeError(f"pull-markdown did not report high fidelity: {pull_markdown_high_result}")
            high_pulled_file = pull_markdown_high_root / "imports" / "high-root-a.md"
            high_pulled_text = high_pulled_file.read_text(encoding="utf-8")
            for expected_fragment in (
                "feishu_pull_fidelity: blocks",
                "## Architecture",
                "High fidelity **paragraph** from blocks.",
                "- First bullet",
                "1. First ordered step",
                "> Important note from the block tree.",
                "```bash",
                "echo \"smoke\"",
                "> [!CALLOUT]",
                "> Review this callout.",
                "| Column A | Column B |",
                "![Architecture diagram](feishu-media:box-root-a-image)",
                "[Architecture.pdf](feishu-file:box-root-a-file)",
            ):
                if expected_fragment not in high_pulled_text:
                    raise RuntimeError(f"High-fidelity pull-markdown missed expected content {expected_fragment!r}: {high_pulled_text}")
            high_pull_index_payload = json.loads((pull_markdown_high_root / "feishu-index.json").read_text(encoding="utf-8"))
            if high_pull_index_payload.get("files", [{}])[0].get("last_pull_fidelity") != "blocks":
                raise RuntimeError(f"High-fidelity pull-markdown did not persist block fidelity into the index: {high_pull_index_payload}")

            pull_markdown_user_root = Path(tmp_dir) / "pull-root-user"
            pull_markdown_user_result = json.loads(
                run_cli(
                    "pull-markdown",
                    "dox-root-b",
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--root",
                    str(pull_markdown_user_root),
                    "--relative-path",
                    "imports/user-root-b.md",
                    env=user_env,
                )
            )
            if not pull_markdown_user_result.get("ok") or pull_markdown_user_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode pull-markdown result: {pull_markdown_user_result}")
            user_pulled_file = pull_markdown_user_root / "imports" / "user-root-b.md"
            if not user_pulled_file.is_file():
                raise RuntimeError("user-mode pull-markdown did not create the expected local Markdown file")
            if "Root B content." not in user_pulled_file.read_text(encoding="utf-8"):
                raise RuntimeError(f"Unexpected user-mode pull-markdown file content: {user_pulled_file.read_text(encoding='utf-8')}")

            pull_dir_root = Path(tmp_dir) / "pull-dir-root"
            pull_dir_result = json.loads(
                run_cli(
                    "pull-dir",
                    str(pull_dir_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not pull_dir_result.get("ok"):
                raise RuntimeError(f"Unexpected pull-dir result: {pull_dir_result}")
            if pull_dir_result.get("result", {}).get("pulled_count") != 5:
                raise RuntimeError(f"Unexpected pull-dir pulled_count: {pull_dir_result}")
            pull_dir_index = pull_dir_root / "feishu-index.json"
            pull_dir_index_payload = json.loads(pull_dir_index.read_text(encoding="utf-8"))
            if len(pull_dir_index_payload.get("files", [])) != 5:
                raise RuntimeError(f"Unexpected pull-dir index payload: {pull_dir_index_payload}")
            nested_pull_file = pull_dir_root / "Team-Notes" / "Archive" / "Archive-Note.md"
            if not nested_pull_file.is_file():
                raise RuntimeError("pull-dir did not create the expected nested Markdown file")
            mirrored_pull_file = pull_dir_root / "Guides" / "API" / "Intro-Guide.md"
            if not mirrored_pull_file.is_file():
                raise RuntimeError("pull-dir did not create the expected mirrored nested Markdown file")

            pull_dir_high_root = Path(tmp_dir) / "pull-dir-root-high"
            pull_dir_high_result = json.loads(
                run_cli(
                    "pull-dir",
                    str(pull_dir_high_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--fidelity",
                    "high",
                )
            )
            if not pull_dir_high_result.get("ok"):
                raise RuntimeError(f"Unexpected high-fidelity pull-dir result: {pull_dir_high_result}")
            pull_dir_high_payload = pull_dir_high_result.get("result", {})
            if pull_dir_high_payload.get("fidelity") != "high" or pull_dir_high_payload.get("pulled_count") != 5:
                raise RuntimeError(f"Unexpected high-fidelity pull-dir payload: {pull_dir_high_result}")
            high_dir_file = pull_dir_high_root / "Mock-Root-Doc-A.md"
            if "feishu_pull_fidelity: blocks" not in high_dir_file.read_text(encoding="utf-8"):
                raise RuntimeError("pull-dir --fidelity high did not persist block-export front matter")

            pull_dir_user_root = Path(tmp_dir) / "pull-dir-root-user"
            pull_dir_user_result = json.loads(
                run_cli(
                    "pull-dir",
                    str(pull_dir_user_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    env=user_env,
                )
            )
            if not pull_dir_user_result.get("ok") or pull_dir_user_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode pull-dir result: {pull_dir_user_result}")
            if pull_dir_user_result.get("result", {}).get("pulled_count") != 5:
                raise RuntimeError(f"Unexpected user-mode pull-dir pulled_count: {pull_dir_user_result}")

            media_file = Path(tmp_dir) / "diagram.png"
            media_file.write_bytes(b"\x89PNG\r\n\x1a\nmock-image-data")
            upload_media_result = json.loads(
                run_cli(
                    "upload-media",
                    "dox-mock",
                    str(media_file),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--file-name",
                    "architecture.png",
                    "--extra-drive-route-token",
                    "fld-root-mock",
                )
            )
            if not upload_media_result.get("ok"):
                raise RuntimeError(f"Unexpected upload-media result: {upload_media_result}")
            upload_payload = upload_media_result.get("result", {})
            if not str(upload_payload.get("file_token") or "").startswith("box-mock-"):
                raise RuntimeError(f"upload-media did not return a mock file token: {upload_media_result}")
            last_upload = MockFeishuHandler.media_uploads[-1] if MockFeishuHandler.media_uploads else {}
            if last_upload.get("document_id") != "dox-mock" or last_upload.get("parent_type") != "docx_image":
                raise RuntimeError(f"upload-media did not preserve document routing fields: {last_upload}")
            if last_upload.get("file_name") != "architecture.png" or last_upload.get("size") != str(media_file.stat().st_size):
                raise RuntimeError(f"upload-media did not preserve file metadata: {last_upload}")

            media_push_root = Path(tmp_dir) / "push-media"
            (media_push_root / "assets").mkdir(parents=True, exist_ok=True)
            (media_push_root / "assets" / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\nmedia-image-data")
            (media_push_root / "assets" / "spec.pdf").write_bytes(b"%PDF-1.4 mock attachment")
            media_push_file = media_push_root / "media.md"
            media_push_file.write_text(
                "# Media Push\n\n"
                "![Diagram](assets/diagram.png)\n\n"
                "[Spec PDF](assets/spec.pdf)\n\n"
                "Body after uploaded media.\n",
                encoding="utf-8",
            )
            media_push_result = json.loads(
                run_cli(
                    "push-markdown",
                    str(media_push_file),
                    "--root",
                    str(media_push_root),
                    "--upload-media",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not media_push_result.get("ok"):
                raise RuntimeError(f"Unexpected push-markdown --upload-media result: {media_push_result}")
            media_push_payload = media_push_result.get("result", {})
            media_backfill = (((media_push_payload.get("write") or {}).get("append") or {}).get("media_backfill") or {})
            if media_backfill.get("uploaded_count") != 2:
                raise RuntimeError(f"push-markdown --upload-media did not report the uploaded media count: {media_push_result}")
            latest_uploads = MockFeishuHandler.media_uploads[-2:]
            latest_parent_types = [item.get("parent_type") for item in latest_uploads]
            if latest_parent_types != ["docx_image", "docx_file"]:
                raise RuntimeError(f"push-markdown --upload-media did not route image and attachment uploads correctly: {latest_uploads}")
            latest_descendant_request = MockFeishuHandler.descendant_requests[-1] if MockFeishuHandler.descendant_requests else {}
            descendants = ((latest_descendant_request.get("payload") or {}).get("descendants") or [])
            image_blocks = [item for item in descendants if isinstance(item, dict) and item.get("block_type") == 27]
            file_blocks = [item for item in descendants if isinstance(item, dict) and item.get("block_type") == 23]
            if not image_blocks or not file_blocks:
                raise RuntimeError(f"push-markdown --upload-media did not synthesize image/file blocks: {latest_descendant_request}")
            if not str((image_blocks[0].get("image") or {}).get("token") or "").startswith("box-mock-"):
                raise RuntimeError(f"Media image block did not carry the uploaded token: {image_blocks[0]}")
            if not str((file_blocks[0].get("file") or {}).get("token") or "").startswith("box-mock-"):
                raise RuntimeError(f"Media attachment block did not carry the uploaded token: {file_blocks[0]}")

            sync_root = Path(tmp_dir) / "sync-root"
            sync_root.mkdir(parents=True, exist_ok=True)
            (sync_root / "mapped.md").write_text(
                "---\n"
                "title: Mapped Root A\n"
                "feishu_doc_token: dox-root-a\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# Mapped Root A\n"
                "\n"
                "Keep this file locally.\n",
                encoding="utf-8",
            )
            (sync_root / "feishu-index.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "files": [
                            {
                                "relative_path": "missing.md",
                                "doc_token": "dox-root-b",
                                "title": "Mock Root Doc B",
                                "sync_direction": "push",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            sync_dir_result = json.loads(
                run_cli(
                    "sync-dir",
                    str(sync_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--dry-run",
                    "--prune",
                )
            )
            if not sync_dir_result.get("ok"):
                raise RuntimeError(f"Unexpected sync-dir result: {sync_dir_result}")
            sync_summary = sync_dir_result.get("result", {}).get("summary", {})
            if sync_summary.get("remote_pull_candidate_count") != 3:
                raise RuntimeError(f"Unexpected sync-dir remote pull candidate count: {sync_dir_result}")
            if sync_summary.get("prune_candidate_count") != 1:
                raise RuntimeError(f"Unexpected sync-dir prune candidate count: {sync_dir_result}")
            if sync_summary.get("local_action_counts", {}).get("update_doc") != 1:
                raise RuntimeError(f"Unexpected sync-dir local action counts: {sync_dir_result}")

            MockFeishuHandler.drive_files["fld-user-bidir-suite"] = []
            MockFeishuHandler.documents["dox-user-bidir-local"] = {
                "title": "User Bidir Local",
                "revision_id": 2,
                "children": [],
                "url": "https://example.test/docx/dox-user-bidir-local",
                "raw_content": "User Bidir Local\nRemote snapshot before a user-mode push.\n",
            }
            MockFeishuHandler.documents["dox-user-bidir-remote"] = {
                "title": "User Bidir Remote",
                "revision_id": 5,
                "children": [],
                "url": "https://example.test/docx/dox-user-bidir-remote",
                "raw_content": "User Bidir Remote\nRemote revision that should be pulled by the user-mode sync.\n",
            }
            MockFeishuHandler._register_drive_child(
                "fld-user-bidir-suite",
                {
                    "name": "User Bidir Local",
                    "type": "docx",
                    "token": "dox-user-bidir-local",
                    "parent_token": "fld-user-bidir-suite",
                    "url": "https://example.test/docx/dox-user-bidir-local",
                    "created_time": "1773500100",
                    "modified_time": "1773500101",
                },
            )
            MockFeishuHandler._register_drive_child(
                "fld-user-bidir-suite",
                {
                    "name": "User Bidir Remote",
                    "type": "docx",
                    "token": "dox-user-bidir-remote",
                    "parent_token": "fld-user-bidir-suite",
                    "url": "https://example.test/docx/dox-user-bidir-remote",
                    "created_time": "1773500102",
                    "modified_time": "1773500103",
                },
            )

            user_sync_root = Path(tmp_dir) / "user-sync-root"
            user_sync_root.mkdir(parents=True, exist_ok=True)
            (user_sync_root / "push-user.md").write_text(
                "---\n"
                "title: User Bidir Local\n"
                "feishu_doc_token: dox-user-bidir-local\n"
                "feishu_sync_direction: bidirectional\n"
                "---\n"
                "\n"
                "# User Bidir Local\n"
                "\n"
                "Local version ready for a user-mode push.\n",
                encoding="utf-8",
            )
            (user_sync_root / "pull-user.md").write_text(
                "---\n"
                "title: User Bidir Remote\n"
                "feishu_doc_token: dox-user-bidir-remote\n"
                "feishu_sync_direction: bidirectional\n"
                "---\n"
                "\n"
                "# User Bidir Remote\n"
                "\n"
                "Older local copy.\n",
                encoding="utf-8",
            )
            (user_sync_root / "feishu-index.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "files": [
                            {
                                "relative_path": "push-user.md",
                                "doc_token": "dox-user-bidir-local",
                                "title": "User Bidir Local",
                                "sync_direction": "bidirectional",
                                "body_hash": sha256_text("\n# User Bidir Local\n\nPrevious local push text."),
                                "remote_revision_id": 2,
                                "remote_content_hash": sha256_text(str(MockFeishuHandler.documents["dox-user-bidir-local"]["raw_content"])),
                                "last_sync_at": "2026-03-14T12:40:00Z",
                            },
                            {
                                "relative_path": "pull-user.md",
                                "doc_token": "dox-user-bidir-remote",
                                "title": "User Bidir Remote",
                                "sync_direction": "bidirectional",
                                "body_hash": sha256_text("\n# User Bidir Remote\n\nOlder local copy."),
                                "remote_revision_id": 4,
                                "remote_content_hash": sha256_text("older remote pull snapshot"),
                                "last_sync_at": "2026-03-14T12:45:00Z",
                            },
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            user_sync_dry_run_result = json.loads(
                run_cli(
                    "sync-dir",
                    str(user_sync_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--folder-token",
                    "fld-user-bidir-suite",
                    "--dry-run",
                    "--detect-conflicts",
                    env=user_env,
                )
            )
            if not user_sync_dry_run_result.get("ok") or user_sync_dry_run_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode sync-dir dry-run result: {user_sync_dry_run_result}")
            user_conflict_detection = user_sync_dry_run_result.get("result", {}).get("conflict_detection", {})
            if user_conflict_detection.get("state_counts", {}).get("local_ahead") != 1 or user_conflict_detection.get("state_counts", {}).get("remote_ahead") != 1:
                raise RuntimeError(f"user-mode sync-dir dry-run did not classify one local_ahead and one remote_ahead file: {user_sync_dry_run_result}")

            blocked_user_sync_execute = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "sync-dir",
                    str(user_sync_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--folder-token",
                    "fld-user-bidir-suite",
                    "--execute-bidirectional",
                    "--confirm-bidirectional",
                    "--pull-fidelity",
                    "low",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=user_env,
            )
            if blocked_user_sync_execute.returncode == 0:
                raise RuntimeError(f"user-mode sync-dir should require --confirm-user-write: {blocked_user_sync_execute.stdout}")
            blocked_user_sync_execute_payload = extract_json_object(blocked_user_sync_execute.stdout)
            if "--confirm-user-write" not in str(blocked_user_sync_execute_payload.get("error") or ""):
                raise RuntimeError(f"user-mode sync-dir did not explain the bidirectional write protection failure: {blocked_user_sync_execute_payload}")

            user_sync_execute_result = json.loads(
                run_cli(
                    "sync-dir",
                    str(user_sync_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--folder-token",
                    "fld-user-bidir-suite",
                    "--execute-bidirectional",
                    "--confirm-bidirectional",
                    "--confirm-user-write",
                    "--pull-fidelity",
                    "low",
                    env=user_env,
                )
            )
            if not user_sync_execute_result.get("ok") or user_sync_execute_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode sync-dir execution result: {user_sync_execute_result}")
            user_sync_execute_summary = user_sync_execute_result.get("result", {}).get("summary", {})
            if user_sync_execute_summary.get("pushed_count") != 1 or user_sync_execute_summary.get("pulled_count") != 1:
                raise RuntimeError(f"user-mode sync-dir execution did not run one push and one pull: {user_sync_execute_result}")
            if "Remote revision that should be pulled by the user-mode sync." not in (user_sync_root / "pull-user.md").read_text(encoding="utf-8"):
                raise RuntimeError(f"user-mode sync-dir execution did not pull the remote content into the local file: {user_sync_execute_result}")
            migrated_user_sync_index = user_sync_root / "feishu-index.user.json"
            if not migrated_user_sync_index.is_file():
                raise RuntimeError("user-mode sync-dir execution should migrate writes into feishu-index.user.json when only a legacy generic index existed")
            migrated_user_sync_payload = json.loads(migrated_user_sync_index.read_text(encoding="utf-8"))
            if migrated_user_sync_payload.get("auth_mode") != "user":
                raise RuntimeError(f"user-mode sync-dir execution did not tag the migrated index with user scope metadata: {migrated_user_sync_payload}")

            user_sync_create_root = Path(tmp_dir) / "user-sync-create-root"
            user_sync_create_root.mkdir(parents=True, exist_ok=True)
            (user_sync_create_root / "create-user.md").write_text(
                "---\n"
                "title: User Sync Create\n"
                "feishu_sync_direction: bidirectional\n"
                "---\n"
                "\n"
                "# User Sync Create\n"
                "\n"
                "Create this remote doc from user-mode sync-dir.\n",
                encoding="utf-8",
            )
            blocked_user_sync_create = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "sync-dir",
                    str(user_sync_create_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--folder-token",
                    "fld-user-bidir-suite",
                    "--execute-bidirectional",
                    "--confirm-bidirectional",
                    "--confirm-user-write",
                    "--include-create-flow",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=user_env,
            )
            if blocked_user_sync_create.returncode == 0:
                raise RuntimeError(f"user-mode sync-dir should block create flow without --allow-user-create: {blocked_user_sync_create.stdout}")
            blocked_user_sync_create_payload = extract_json_object(blocked_user_sync_create.stdout)
            if "--allow-user-create" not in str(blocked_user_sync_create_payload.get("error") or ""):
                raise RuntimeError(f"user-mode sync-dir did not explain the protected create flow: {blocked_user_sync_create_payload}")

            user_sync_create_result = json.loads(
                run_cli(
                    "sync-dir",
                    str(user_sync_create_root),
                    "--auth-mode",
                    "user",
                    "--base-url",
                    base_url,
                    "--folder-token",
                    "fld-user-bidir-suite",
                    "--execute-bidirectional",
                    "--confirm-bidirectional",
                    "--confirm-user-write",
                    "--include-create-flow",
                    "--allow-user-create",
                    env=user_env,
                )
            )
            if not user_sync_create_result.get("ok") or user_sync_create_result.get("mode") != "user":
                raise RuntimeError(f"Unexpected user-mode sync-dir create execution result: {user_sync_create_result}")
            user_sync_create_summary = user_sync_create_result.get("result", {}).get("summary", {})
            if user_sync_create_summary.get("pushed_count") != 1 or user_sync_create_summary.get("created_count") != 1:
                raise RuntimeError(f"user-mode sync-dir create flow did not report one created push: {user_sync_create_result}")
            user_sync_create_index_payload = json.loads((user_sync_create_root / "feishu-index.user.json").read_text(encoding="utf-8"))
            user_sync_create_entry = user_sync_create_index_payload.get("files", [{}])[0]
            if not str(user_sync_create_entry.get("doc_token") or "").startswith("dox-created-"):
                raise RuntimeError(f"user-mode sync-dir create flow did not persist the created doc token: {user_sync_create_index_payload}")

            conflict_root = Path(tmp_dir) / "conflict-root"
            conflict_root.mkdir(parents=True, exist_ok=True)
            pull_remote_path = conflict_root / "pull-remote.md"
            pull_remote_path.write_text(
                "---\n"
                "title: Pull Remote\n"
                "feishu_doc_token: dox-root-a\n"
                "feishu_sync_direction: pull\n"
                "---\n"
                "\n"
                "# Pull Remote\n"
                "\n"
                "Keep remote as source.\n",
                encoding="utf-8",
            )
            push_local_path = conflict_root / "push-local.md"
            push_local_path.write_text(
                "---\n"
                "title: Push Local\n"
                "feishu_doc_token: dox-team-note\n"
                "feishu_sync_direction: push\n"
                "---\n"
                "\n"
                "# Push Local\n"
                "\n"
                "Local draft changed.\n",
                encoding="utf-8",
            )
            review_conflict_path = conflict_root / "review-conflict.md"
            review_conflict_path.write_text(
                "---\n"
                "title: Review Conflict\n"
                "feishu_doc_token: dox-archive-note\n"
                "feishu_sync_direction: bidirectional\n"
                "---\n"
                "\n"
                "# Review Conflict\n"
                "\n"
                "Both sides changed.\n",
                encoding="utf-8",
            )
            (conflict_root / "feishu-index.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "files": [
                            {
                                "relative_path": "pull-remote.md",
                                "doc_token": "dox-root-a",
                                "title": "Pull Remote",
                                "sync_direction": "pull",
                                "body_hash": sha256_text("\n# Pull Remote\n\nKeep remote as source."),
                                "remote_revision_id": 2,
                                "remote_content_hash": sha256_text("older remote snapshot"),
                                "last_sync_at": "2026-03-14T12:00:00Z",
                            },
                            {
                                "relative_path": "push-local.md",
                                "doc_token": "dox-team-note",
                                "title": "Push Local",
                                "sync_direction": "push",
                                "body_hash": sha256_text("\n# Push Local\n\nPrevious local draft."),
                                "remote_revision_id": 2,
                                "remote_content_hash": sha256_text(str(MockFeishuHandler.documents["dox-team-note"]["raw_content"])),
                                "last_sync_at": "2026-03-14T12:05:00Z",
                            },
                            {
                                "relative_path": "review-conflict.md",
                                "doc_token": "dox-archive-note",
                                "title": "Review Conflict",
                                "sync_direction": "bidirectional",
                                "body_hash": sha256_text("\n# Review Conflict\n\nPrevious local text."),
                                "baseline_body_snapshot": encode_text_snapshot("\n# Review Conflict\n\nShared baseline text.\n"),
                                "remote_revision_id": 0,
                                "remote_content_hash": sha256_text("much older remote snapshot"),
                                "last_sync_at": "2026-03-14T12:10:00Z",
                            },
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            conflict_detect_result = json.loads(
                run_cli(
                    "sync-dir",
                    str(conflict_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--dry-run",
                    "--detect-conflicts",
                    "--include-diff",
                    "--diff-fidelity",
                    "high",
                    "--diff-max-lines",
                    "20",
                )
            )
            if not conflict_detect_result.get("ok"):
                raise RuntimeError(f"Unexpected sync-dir conflict detection result: {conflict_detect_result}")
            conflict_detection = conflict_detect_result.get("result", {}).get("conflict_detection", {})
            if conflict_detection.get("inspected_count") != 3:
                raise RuntimeError(f"Unexpected inspected_count for sync-dir conflict detection: {conflict_detect_result}")
            state_counts = conflict_detection.get("state_counts", {})
            if state_counts.get("remote_ahead") != 1 or state_counts.get("local_ahead") != 1 or state_counts.get("local_and_remote_changed") != 1:
                raise RuntimeError(f"Unexpected state counts for sync-dir conflict detection: {conflict_detect_result}")
            action_counts = conflict_detection.get("recommended_action_counts", {})
            if action_counts.get("pull_candidate") != 1 or action_counts.get("push_candidate") != 1 or action_counts.get("manual_conflict_review") != 1:
                raise RuntimeError(f"Unexpected recommended actions for sync-dir conflict detection: {conflict_detect_result}")
            diff_summary = conflict_detection.get("diff", {})
            if not diff_summary.get("enabled"):
                raise RuntimeError(f"sync-dir conflict detection did not report diff preview as enabled: {conflict_detect_result}")
            if diff_summary.get("generated_count") != 3 or diff_summary.get("failed_count") != 0:
                raise RuntimeError(f"Unexpected diff preview counts for sync-dir conflict detection: {conflict_detect_result}")
            conflict_summary = conflict_detect_result.get("result", {}).get("summary", {})
            if conflict_summary.get("conflict_review_count") != 1:
                raise RuntimeError(f"Unexpected sync-dir conflict review count: {conflict_detect_result}")
            if conflict_summary.get("conflict_diff_preview_count") != 3:
                raise RuntimeError(f"Unexpected sync-dir diff preview count: {conflict_detect_result}")
            if conflict_summary.get("merge_suggestion_count") != 1 or conflict_summary.get("merge_auto_ready_count") != 0:
                raise RuntimeError(f"Unexpected sync-dir merge suggestion counts: {conflict_detect_result}")
            conflict_results = {
                entry.get("relative_path"): entry
                for entry in conflict_detection.get("results", [])
                if isinstance(entry, dict)
            }
            if conflict_results.get("pull-remote.md", {}).get("comparison", {}).get("recommended_action") != "pull_candidate":
                raise RuntimeError(f"pull-remote.md did not classify as a pull candidate: {conflict_detect_result}")
            if conflict_results.get("push-local.md", {}).get("comparison", {}).get("recommended_action") != "push_candidate":
                raise RuntimeError(f"push-local.md did not classify as a push candidate: {conflict_detect_result}")
            if conflict_results.get("review-conflict.md", {}).get("comparison", {}).get("recommended_action") != "manual_conflict_review":
                raise RuntimeError(f"review-conflict.md did not classify as a manual conflict review case: {conflict_detect_result}")
            pull_remote_diff = conflict_results.get("pull-remote.md", {}).get("diff", {})
            if pull_remote_diff.get("format") != "semantic_blocks":
                raise RuntimeError(f"pull-remote.md did not expose semantic block diff output: {conflict_detect_result}")
            if "heading-2: Architecture" not in str(pull_remote_diff.get("preview") or ""):
                raise RuntimeError(f"pull-remote.md semantic diff preview did not include expected block structure: {conflict_detect_result}")
            review_diff = conflict_results.get("review-conflict.md", {}).get("diff", {})
            if not review_diff.get("ok") or not review_diff.get("has_changes"):
                raise RuntimeError(f"review-conflict.md did not include a usable diff preview: {conflict_detect_result}")
            preview_text = str(review_diff.get("line_preview", {}).get("preview") or "")
            if "--- local:review-conflict.md" not in preview_text or "+++ feishu:dox-archive-note" not in preview_text:
                raise RuntimeError(f"review-conflict.md diff preview headers are missing: {conflict_detect_result}")
            if "Both sides changed." not in preview_text or "Archived nested content." not in preview_text:
                raise RuntimeError(f"review-conflict.md diff preview did not include expected changed content: {conflict_detect_result}")
            review_merge = conflict_results.get("review-conflict.md", {}).get("merge_suggestion", {})
            if not review_merge.get("ok") or review_merge.get("auto_merge_ready"):
                raise RuntimeError(f"review-conflict.md did not expose a blocked semantic merge suggestion: {conflict_detect_result}")
            if not review_merge.get("baseline_available") or review_merge.get("summary", {}).get("conflict_count", 0) < 1:
                raise RuntimeError(f"review-conflict.md merge suggestion did not preserve the expected baseline/conflict metadata: {conflict_detect_result}")

            MockFeishuHandler.documents["dox-bidir-local"] = {
                "title": "Bidir Local",
                "revision_id": 2,
                "children": [],
                "url": "https://example.test/docx/dox-bidir-local",
                "raw_content": "Bidir Local\nRemote snapshot before push.\n",
            }
            MockFeishuHandler.documents["dox-bidir-remote"] = {
                "title": "Bidir Remote",
                "revision_id": 5,
                "children": [],
                "url": "https://example.test/docx/dox-bidir-remote",
                "raw_content": "Bidir Remote\nRemote revision that should be pulled.\n",
            }
            MockFeishuHandler.documents["dox-bidir-conflict"] = {
                "title": "Bidir Conflict",
                "revision_id": 7,
                "children": [],
                "url": "https://example.test/docx/dox-bidir-conflict",
                "raw_content": "Bidir Conflict\nRemote conflict text.\n",
            }
            MockFeishuHandler._register_drive_child(
                "fld-root-mock",
                {
                    "name": "Bidir Local",
                    "type": "docx",
                    "token": "dox-bidir-local",
                    "parent_token": "fld-root-mock",
                    "url": "https://example.test/docx/dox-bidir-local",
                    "created_time": "1773500012",
                    "modified_time": "1773500013",
                },
            )
            MockFeishuHandler._register_drive_child(
                "fld-root-mock",
                {
                    "name": "Bidir Remote",
                    "type": "docx",
                    "token": "dox-bidir-remote",
                    "parent_token": "fld-root-mock",
                    "url": "https://example.test/docx/dox-bidir-remote",
                    "created_time": "1773500014",
                    "modified_time": "1773500015",
                },
            )
            MockFeishuHandler._register_drive_child(
                "fld-root-mock",
                {
                    "name": "Bidir Conflict",
                    "type": "docx",
                    "token": "dox-bidir-conflict",
                    "parent_token": "fld-root-mock",
                    "url": "https://example.test/docx/dox-bidir-conflict",
                    "created_time": "1773500016",
                    "modified_time": "1773500017",
                },
            )

            blocked_bidir_root = Path(tmp_dir) / "blocked-bidir-root"
            blocked_bidir_root.mkdir(parents=True, exist_ok=True)
            (blocked_bidir_root / "needs-review.md").write_text(
                "---\n"
                "title: Bidir Conflict\n"
                "feishu_doc_token: dox-bidir-conflict\n"
                "feishu_sync_direction: bidirectional\n"
                "---\n"
                "\n"
                "# Bidir Conflict\n"
                "\n"
                "Local conflict text.\n",
                encoding="utf-8",
            )
            (blocked_bidir_root / "feishu-index.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "files": [
                            {
                                "relative_path": "needs-review.md",
                                "doc_token": "dox-bidir-conflict",
                                "title": "Bidir Conflict",
                                "sync_direction": "bidirectional",
                                "body_hash": sha256_text("\n# Bidir Conflict\n\nPrevious local conflict text."),
                                "remote_revision_id": 6,
                                "remote_content_hash": sha256_text("older remote conflict snapshot"),
                                "last_sync_at": "2026-03-14T12:20:00Z",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            blocked_execution = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "sync-dir",
                    str(blocked_bidir_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--execute-bidirectional",
                    "--confirm-bidirectional",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            if blocked_execution.returncode == 0:
                raise RuntimeError(f"Protected bidirectional execution should have been blocked: {blocked_execution.stdout}")
            blocked_payload = extract_json_object(blocked_execution.stdout)
            if "blocked" not in str(blocked_payload.get("error") or ""):
                raise RuntimeError(f"Blocked bidirectional execution did not explain the protection failure: {blocked_payload}")
            blocked_plan_summary = blocked_payload.get("result", {}).get("execution_plan", {}).get("summary", {})
            if blocked_plan_summary.get("blocked_count") != 1 or blocked_plan_summary.get("actionable_count") != 0:
                raise RuntimeError(f"Blocked bidirectional execution did not report the expected protection counts: {blocked_payload}")

            clean_bidir_root = Path(tmp_dir) / "clean-bidir-root"
            clean_bidir_root.mkdir(parents=True, exist_ok=True)
            (clean_bidir_root / "push-clean.md").write_text(
                "---\n"
                "title: Bidir Local\n"
                "feishu_doc_token: dox-bidir-local\n"
                "feishu_sync_direction: bidirectional\n"
                "---\n"
                "\n"
                "# Bidir Local\n"
                "\n"
                "Local version ready to push.\n",
                encoding="utf-8",
            )
            (clean_bidir_root / "pull-clean.md").write_text(
                "---\n"
                "title: Bidir Remote\n"
                "feishu_doc_token: dox-bidir-remote\n"
                "feishu_sync_direction: bidirectional\n"
                "---\n"
                "\n"
                "# Bidir Remote\n"
                "\n"
                "Older local copy.\n",
                encoding="utf-8",
            )
            (clean_bidir_root / "feishu-index.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "files": [
                            {
                                "relative_path": "push-clean.md",
                                "doc_token": "dox-bidir-local",
                                "title": "Bidir Local",
                                "sync_direction": "bidirectional",
                                "body_hash": sha256_text("\n# Bidir Local\n\nPrevious local push text."),
                                "remote_revision_id": 2,
                                "remote_content_hash": sha256_text(str(MockFeishuHandler.documents["dox-bidir-local"]["raw_content"])),
                                "last_sync_at": "2026-03-14T12:25:00Z",
                            },
                            {
                                "relative_path": "pull-clean.md",
                                "doc_token": "dox-bidir-remote",
                                "title": "Bidir Remote",
                                "sync_direction": "bidirectional",
                                "body_hash": sha256_text("\n# Bidir Remote\n\nOlder local copy."),
                                "remote_revision_id": 4,
                                "remote_content_hash": sha256_text("older remote pull snapshot"),
                                "last_sync_at": "2026-03-14T12:30:00Z",
                            },
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            bidirectional_execute_result = json.loads(
                run_cli(
                    "sync-dir",
                    str(clean_bidir_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--execute-bidirectional",
                    "--confirm-bidirectional",
                    "--pull-fidelity",
                    "low",
                )
            )
            if not bidirectional_execute_result.get("ok"):
                raise RuntimeError(f"Unexpected protected bidirectional execution result: {bidirectional_execute_result}")
            bidirectional_payload = bidirectional_execute_result.get("result", {})
            bidirectional_summary = bidirectional_payload.get("summary", {})
            if bidirectional_summary.get("pushed_count") != 1 or bidirectional_summary.get("pulled_count") != 1:
                raise RuntimeError(f"Protected bidirectional execution did not run one push and one pull: {bidirectional_execute_result}")
            if bidirectional_summary.get("failed_count") != 0:
                raise RuntimeError(f"Protected bidirectional execution reported unexpected failures: {bidirectional_execute_result}")
            bidirectional_plan_summary = bidirectional_payload.get("execution_plan", {}).get("summary", {})
            if bidirectional_plan_summary.get("blocked_count") != 0 or bidirectional_plan_summary.get("actionable_count") != 2:
                raise RuntimeError(f"Protected bidirectional execution did not report the expected action plan: {bidirectional_execute_result}")
            bidirectional_backup_dir = Path(bidirectional_payload.get("backup", {}).get("run_dir", ""))
            if not bidirectional_backup_dir.is_dir():
                raise RuntimeError(f"Protected bidirectional execution did not create a backup directory: {bidirectional_execute_result}")
            if not (bidirectional_backup_dir / "bidirectional-execution-plan.json").is_file():
                raise RuntimeError(f"Protected bidirectional execution did not write the execution plan snapshot: {bidirectional_execute_result}")
            if not any(path.name == "document.md" for path in (bidirectional_backup_dir / "remote-before-push").rglob("document.md")):
                raise RuntimeError(f"Protected bidirectional execution did not back up the remote push target: {bidirectional_execute_result}")
            if not (bidirectional_backup_dir / "local-files" / "pull-clean.md").is_file():
                raise RuntimeError(f"Protected bidirectional execution did not back up the local pull target: {bidirectional_execute_result}")
            pulled_text = (clean_bidir_root / "pull-clean.md").read_text(encoding="utf-8")
            if "Remote revision that should be pulled." not in pulled_text:
                raise RuntimeError(f"Protected bidirectional execution did not pull the remote content into the local file: {bidirectional_execute_result}")
            if int(MockFeishuHandler.documents["dox-bidir-local"]["revision_id"]) <= 2:
                raise RuntimeError("Protected bidirectional execution did not update the remote push target revision")
            clean_index_payload = json.loads((clean_bidir_root / "feishu-index.json").read_text(encoding="utf-8"))
            clean_entries = {
                entry.get("relative_path"): entry
                for entry in clean_index_payload.get("files", [])
                if isinstance(entry, dict)
            }
            if clean_entries.get("push-clean.md", {}).get("last_sync_operation") != "push":
                raise RuntimeError(f"Protected bidirectional execution did not mark the push result in the index: {clean_index_payload}")
            if clean_entries.get("pull-clean.md", {}).get("last_sync_operation") != "pull":
                raise RuntimeError(f"Protected bidirectional execution did not mark the pull result in the index: {clean_index_payload}")
            if clean_entries.get("pull-clean.md", {}).get("last_pull_fidelity") != "raw_content":
                raise RuntimeError(f"Protected bidirectional execution did not persist pull fidelity in the index: {clean_index_payload}")

            MockFeishuHandler.drive_files["fld-bidir-suite"] = []
            MockFeishuHandler.documents["dox-bidir-merge"] = {
                "title": "Bidir Merge",
                "revision_id": 8,
                "children": ["blk-dox-bidir-merge-1", "blk-dox-bidir-merge-2", "blk-dox-bidir-merge-3"],
                "url": "https://example.test/docx/dox-bidir-merge",
                "raw_content": "Bidir Merge\nIntro paragraph.\n\nShared ending.\n\nRemote appendix.\n",
                "blocks": make_mock_document_blocks(
                    "dox-bidir-merge",
                    "Bidir Merge",
                    ["Intro paragraph.", "Shared ending.", "Remote appendix."],
                ),
            }
            MockFeishuHandler.documents["dox-bidir-adopt"] = {
                "title": "Bidir Adopt",
                "revision_id": 3,
                "children": ["blk-dox-bidir-adopt-1"],
                "url": "https://example.test/docx/dox-bidir-adopt",
                "raw_content": "Bidir Adopt\nRemote-only candidate.\n",
                "blocks": make_mock_document_blocks(
                    "dox-bidir-adopt",
                    "Bidir Adopt",
                    ["Remote-only candidate."],
                ),
            }
            MockFeishuHandler._register_drive_child(
                "fld-bidir-suite",
                {
                    "name": "Bidir Merge",
                    "type": "docx",
                    "token": "dox-bidir-merge",
                    "parent_token": "fld-bidir-suite",
                    "url": "https://example.test/docx/dox-bidir-merge",
                    "created_time": "1773500018",
                    "modified_time": "1773500019",
                },
            )
            MockFeishuHandler._register_drive_child(
                "fld-bidir-suite",
                {
                    "name": "Bidir Adopt",
                    "type": "docx",
                    "token": "dox-bidir-adopt",
                    "parent_token": "fld-bidir-suite",
                    "url": "https://example.test/docx/dox-bidir-adopt",
                    "created_time": "1773500020",
                    "modified_time": "1773500021",
                },
            )

            advanced_bidir_root = Path(tmp_dir) / "advanced-bidir-root"
            advanced_bidir_root.mkdir(parents=True, exist_ok=True)
            (advanced_bidir_root / "merge-safe.md").write_text(
                "---\n"
                "title: Bidir Merge\n"
                "feishu_doc_token: dox-bidir-merge\n"
                "feishu_sync_direction: bidirectional\n"
                "---\n"
                "\n"
                "# Bidir Merge\n"
                "\n"
                "Intro paragraph.\n"
                "\n"
                "Local checklist item.\n"
                "\n"
                "Shared ending.\n",
                encoding="utf-8",
            )
            (advanced_bidir_root / "create-new.md").write_text(
                "---\n"
                "title: Create Bidir\n"
                "feishu_sync_direction: bidirectional\n"
                "---\n"
                "\n"
                "# Create Bidir\n"
                "\n"
                "Local file that should create a remote doc.\n",
                encoding="utf-8",
            )
            (advanced_bidir_root / "feishu-index.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "files": [
                            {
                                "relative_path": "merge-safe.md",
                                "doc_token": "dox-bidir-merge",
                                "title": "Bidir Merge",
                                "sync_direction": "bidirectional",
                                "body_hash": sha256_text("\n# Bidir Merge\n\nIntro paragraph.\n\nShared ending.\n"),
                                "baseline_body_snapshot": encode_text_snapshot("\n# Bidir Merge\n\nIntro paragraph.\n\nShared ending.\n"),
                                "remote_revision_id": 7,
                                "remote_content_hash": sha256_text("older remote merge snapshot"),
                                "last_sync_at": "2026-03-14T12:35:00Z",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            advanced_bidir_result = json.loads(
                run_cli(
                    "sync-dir",
                    str(advanced_bidir_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--folder-token",
                    "fld-bidir-suite",
                    "--execute-bidirectional",
                    "--confirm-bidirectional",
                    "--allow-auto-merge",
                    "--adopt-remote-new",
                    "--include-create-flow",
                    "--pull-fidelity",
                    "high",
                )
            )
            if not advanced_bidir_result.get("ok"):
                raise RuntimeError(f"Unexpected advanced protected bidirectional execution result: {advanced_bidir_result}")
            advanced_payload = advanced_bidir_result.get("result", {})
            advanced_summary = advanced_payload.get("summary", {})
            if (
                advanced_summary.get("pushed_count") != 2
                or advanced_summary.get("pulled_count") != 1
                or advanced_summary.get("merged_count") != 1
                or advanced_summary.get("created_count") != 1
                or advanced_summary.get("adopted_count") != 1
            ):
                raise RuntimeError(f"Advanced bidirectional execution did not report the expected action counts: {advanced_bidir_result}")
            advanced_plan_summary = advanced_payload.get("execution_plan", {}).get("summary", {})
            if advanced_plan_summary.get("blocked_count") != 0 or advanced_plan_summary.get("actionable_count") != 3:
                raise RuntimeError(f"Advanced bidirectional execution did not report the expected protected action plan: {advanced_bidir_result}")
            advanced_backup_dir = Path(advanced_payload.get("backup", {}).get("run_dir", ""))
            if not advanced_backup_dir.is_dir():
                raise RuntimeError(f"Advanced bidirectional execution did not create a backup directory: {advanced_bidir_result}")
            if not (advanced_backup_dir / "local-files" / "merge-safe.md").is_file():
                raise RuntimeError(f"Advanced bidirectional execution did not back up the local merge file: {advanced_bidir_result}")
            if not any(path.name == "document.md" for path in (advanced_backup_dir / "remote-before-merge-push").rglob("document.md")):
                raise RuntimeError(f"Advanced bidirectional execution did not back up the remote merge target: {advanced_bidir_result}")
            merged_text = (advanced_bidir_root / "merge-safe.md").read_text(encoding="utf-8")
            if "Local checklist item." not in merged_text or "Remote appendix." not in merged_text:
                raise RuntimeError(f"Advanced bidirectional execution did not persist the merged Markdown body locally: {advanced_bidir_result}")
            adopted_path = advanced_bidir_root / "Bidir-Adopt.md"
            if not adopted_path.is_file():
                raise RuntimeError(f"Advanced bidirectional execution did not create the adopted remote Markdown file: {advanced_bidir_result}")
            adopted_text = adopted_path.read_text(encoding="utf-8")
            if "feishu_sync_direction: bidirectional" not in adopted_text or "Remote-only candidate." not in adopted_text:
                raise RuntimeError(f"Advanced bidirectional execution did not preserve the adopted remote doc content or mapping metadata: {advanced_bidir_result}")
            advanced_index_payload = json.loads((advanced_bidir_root / "feishu-index.json").read_text(encoding="utf-8"))
            advanced_entries = {
                entry.get("relative_path"): entry
                for entry in advanced_index_payload.get("files", [])
                if isinstance(entry, dict)
            }
            created_entry = advanced_entries.get("create-new.md", {})
            if not str(created_entry.get("doc_token") or "").startswith("dox-created-"):
                raise RuntimeError(f"Advanced bidirectional execution did not persist the newly created remote doc token: {advanced_index_payload}")
            if created_entry.get("last_sync_operation") != "push":
                raise RuntimeError(f"Advanced bidirectional execution did not mark the create flow as a push in the index: {advanced_index_payload}")
            adopted_entry = advanced_entries.get("Bidir-Adopt.md", {})
            if adopted_entry.get("doc_token") != "dox-bidir-adopt" or adopted_entry.get("sync_direction") != "bidirectional":
                raise RuntimeError(f"Advanced bidirectional execution did not persist the adopted remote mapping in the index: {advanced_index_payload}")
            merged_entry = advanced_entries.get("merge-safe.md", {})
            if merged_entry.get("last_sync_operation") != "push":
                raise RuntimeError(f"Advanced bidirectional execution did not persist the merged push result in the index: {advanced_index_payload}")
            if int(MockFeishuHandler.documents["dox-bidir-merge"]["revision_id"]) <= 8:
                raise RuntimeError("Advanced bidirectional execution did not update the remote merge target revision")
            if created_entry.get("doc_token") not in MockFeishuHandler.documents:
                raise RuntimeError(f"Advanced bidirectional execution created an index entry without a backing mock document: {advanced_index_payload}")

            sync_dir_execute_result = json.loads(
                run_cli(
                    "sync-dir",
                    str(sync_root),
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--prune",
                    "--confirm-prune",
                )
            )
            if not sync_dir_execute_result.get("ok"):
                raise RuntimeError(f"Unexpected sync-dir prune execution result: {sync_dir_execute_result}")
            sync_execute_payload = sync_dir_execute_result.get("result", {})
            sync_execute_summary = sync_execute_payload.get("summary", {})
            if sync_execute_summary.get("pruned_count") != 1:
                raise RuntimeError(f"Unexpected sync-dir pruned_count: {sync_dir_execute_result}")
            if sync_execute_summary.get("index_removed_count") != 1:
                raise RuntimeError(f"Unexpected sync-dir index_removed_count: {sync_dir_execute_result}")
            backup_run_dir = Path(sync_execute_payload.get("backup", {}).get("run_dir", ""))
            if not backup_run_dir.is_dir():
                raise RuntimeError(f"sync-dir prune execution did not create a backup directory: {sync_dir_execute_result}")
            if not (backup_run_dir / "sync-dir-plan.json").is_file():
                raise RuntimeError(f"sync-dir prune execution did not write the plan snapshot: {sync_dir_execute_result}")
            if not (backup_run_dir / "index" / "feishu-index.json").is_file():
                raise RuntimeError(f"sync-dir prune execution did not write the index snapshot: {sync_dir_execute_result}")
            backup_doc_md = backup_run_dir / "remote-docs" / "missing.md-root-b" / "document.md"
            if not backup_doc_md.is_file():
                raise RuntimeError(f"sync-dir prune execution did not back up the remote doc: {sync_dir_execute_result}")
            sync_root_index_payload = json.loads((sync_root / "feishu-index.json").read_text(encoding="utf-8"))
            if sync_root_index_payload.get("files") != []:
                raise RuntimeError(f"sync-dir prune execution did not clear the missing index entry: {sync_root_index_payload}")
            if "dox-root-b" in MockFeishuHandler.documents:
                raise RuntimeError("sync-dir prune execution did not delete the remote document")

            delete_result = json.loads(
                run_cli(
                    "delete-document",
                    "dox-mock",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                )
            )
            if not delete_result.get("ok"):
                raise RuntimeError(f"Unexpected delete-document result: {delete_result}")

            exchange_result = json.loads(
                run_cli(
                    "exchange-user-token",
                    "mock_auth_code",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--redirect-uri",
                    "https://example.test/callback",
                )
            )
            if not exchange_result.get("ok"):
                raise RuntimeError(f"Unexpected exchange-user-token result: {exchange_result}")
            token_bundle = exchange_result.get("result", {}).get("token_bundle", {})
            if "access_token" not in token_bundle or "refresh_token" not in token_bundle:
                raise RuntimeError(f"exchange-user-token did not return token previews: {exchange_result}")

            callback_port = get_free_port()
            authorize_process = subprocess.Popen(
                [
                    sys.executable,
                    str(CLI),
                    "authorize-local",
                    "--app-id",
                    "cli_mock",
                    "--app-secret",
                    "mock_secret",
                    "--base-url",
                    base_url,
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(callback_port),
                    "--callback-path",
                    "/callback",
                    "--state",
                    "state123",
                    "--timeout",
                    "10",
                    "--request-timeout",
                    "5",
                    "--no-open-browser",
                ],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.time() + 5
                while time.time() < deadline:
                    try:
                        with socket.create_connection(("127.0.0.1", callback_port), timeout=0.2):
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("authorize-local did not start the local callback server in time")

                with urllib.request.urlopen(
                    f"http://127.0.0.1:{callback_port}/callback?code=mock_auth_code&state=state123",
                    timeout=5,
                ) as callback_response:
                    callback_html = callback_response.read().decode("utf-8", "replace")
                if "Authorization Received" not in callback_html:
                    raise RuntimeError(f"Unexpected callback HTML: {callback_html}")

                stdout, stderr = authorize_process.communicate(timeout=15)
            finally:
                if authorize_process.poll() is None:
                    authorize_process.kill()
                    authorize_process.communicate(timeout=5)

            if authorize_process.returncode != 0:
                raise RuntimeError(
                    "authorize-local failed\n"
                    f"stdout:\n{stdout}\n"
                    f"stderr:\n{stderr}"
                )
            authorize_result = extract_json_object(stdout)
            if not authorize_result.get("ok"):
                raise RuntimeError(f"Unexpected authorize-local result: {authorize_result}")
            authorize_token_bundle = authorize_result.get("result", {}).get("token_bundle", {})
            if "access_token" not in authorize_token_bundle:
                raise RuntimeError(f"authorize-local did not return a token bundle: {authorize_result}")
        finally:
            server.shutdown()
            server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline checks for the Feishu Doc Sync skill.")
    parser.add_argument("--validator", default=str(default_validator_path()), help="Path to skill-creator quick_validate.py.")
    parser.add_argument("--skip-selftest", action="store_true", help="Skip the offline Feishu mock self-tests.")
    parser.add_argument("--skip-validate", action="store_true", help="Skip skill-creator validation.")
    parser.add_argument("--skip-help-smoke", action="store_true", help="Skip CLI --help smoke tests.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not args.skip_selftest:
        print("==> Offline self-tests")
        run_selftest()
        print("Feishu offline self-tests passed.")

    if not args.skip_validate:
        validator_path = resolve_validator_path(args.validator)
        if not validator_path.exists():
            raise SystemExit(f"Validator script not found: {validator_path}. Pass --validator or --skip-validate.")
        run_step("Skill validation", [sys.executable, str(validator_path), str(ROOT)])

    if not args.skip_help_smoke:
        help_commands = [
            ("CLI help", [sys.executable, str(CLI), "--help"]),
            ("Tenant validate help", [sys.executable, str(CLI), "validate-tenant", "--help"]),
            ("User validate help", [sys.executable, str(CLI), "validate-user", "--help"]),
            ("Directory sync help", [sys.executable, str(CLI), "sync-dir", "--help"]),
            ("Directory push help", [sys.executable, str(CLI), "push-dir", "--help"]),
            ("Authorize-local help", [sys.executable, str(CLI), "authorize-local", "--help"]),
        ]
        for label, command in help_commands:
            run_step(label, command)

    print("All Feishu skill checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

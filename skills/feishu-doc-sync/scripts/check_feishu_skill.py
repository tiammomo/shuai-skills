#!/usr/bin/env python3
"""Local smoke checks for the feishu-doc-sync scaffold."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "feishu_doc_sync.py"


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


class MockFeishuHandler(BaseHTTPRequestHandler):
    documents = {
        "dox-mock": {
            "title": "Mock Document",
            "revision_id": 1,
            "children": ["blk-heading", "blk-paragraph"],
            "url": "https://example.test/docx/dox-mock",
        }
    }
    create_counter = 0

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", "replace")
        if not raw:
            return {}
        return json.loads(raw)

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
            MockFeishuHandler.documents[document_id] = {
                "title": title,
                "revision_id": 1,
                "children": [],
                "url": f"https://example.test/docx/{document_id}",
            }
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
            if document_id in MockFeishuHandler.documents:
                title = MockFeishuHandler.documents[document_id]["title"]
            else:
                title = "Mock Document"
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "content": f"{title}\nHello from raw content.\n",
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
            self._write_json(
                200,
                {
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "items": [
                            {
                                "block_id": document_id,
                                "block_type": 1,
                                "children": list(document.get("children", [])),
                            }
                        ],
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
            if folder_token == "fld-root-mock":
                self._write_json(
                    200,
                    {
                        "code": 0,
                        "msg": "ok",
                        "data": {
                            "has_more": False,
                            "next_page_token": None,
                            "files": [
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
                            ],
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
            self._write_json(200, {"code": 0, "msg": "ok", "data": {}})
            return

        self._write_json(404, {"code": 404, "msg": "not found"})


def start_mock_server() -> Tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockFeishuHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def main() -> int:
    run_cli("--help")

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
            if not root_list_result.get("ok") or root_list_result.get("result", {}).get("file_count") != 2:
                raise RuntimeError(f"Unexpected list-root-files result: {root_list_result}")

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

    print("feishu-doc-sync scaffold checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

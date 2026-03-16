#!/usr/bin/env python3
"""Feishu Markdown sync CLI for auth validation, live tenant writes, and planning.

This script currently supports:

- prerequisite checks
- token fetching and auth validation
- browser auth URL generation and local callback capture for user tokens
- tenant-mode docx document creation, lookup, raw-content reads, replacement, append, and deletion
- root-folder and drive file listing
- front matter and index parsing
- local sync planning for files and directories
- tenant-mode push execution for one Markdown file or a whole directory with feishu-index.json write-back
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import difflib
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
import re
import secrets
import shutil
import threading
import uuid
import webbrowser
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

INDEX_FILENAME = "feishu-index.json"
SYNC_BACKUP_DIRNAME = ".feishu-sync-backups"
REQUIRED_ENV = ("FEISHU_APP_ID", "FEISHU_APP_SECRET")
OPTIONAL_TOKEN_ENV = (
    "FEISHU_APP_ACCESS_TOKEN",
    "FEISHU_TENANT_ACCESS_TOKEN",
    "FEISHU_USER_ACCESS_TOKEN",
)
OPTIONAL_ENV = ("FEISHU_BASE_URL", "FEISHU_REDIRECT_URI")
VALID_SYNC_DIRECTIONS = {"push", "pull", "bidirectional"}
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv", ".feishu-sync-backups"}

RECOMMENDED_SCOPES = {
    "write_docx": ["docx:document"],
    "read_docx": ["docx:document:readonly"],
    "convert_markdown": ["docx:document.block:convert"],
    "upload_doc_media": ["docs:document.media:upload"],
    "folder_sync": [
        "space:folder:create",
        "space:document:retrieve",
        "drive:drive.metadata:readonly",
    ],
    "wiki_sync": ["wiki:node:read", "wiki:node:create", "wiki:node:update"],
}

TOKEN_DOCS = {
    "choose_token_type": "https://open.feishu.cn/document/uAjLw4CM/ugTN1YjL4UTN24CO1UjN/trouble-shooting/how-to-choose-which-type-of-token-to-use",
    "app_access_token_internal": "https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/auth-v3/auth/app_access_token_internal",
    "tenant_access_token_internal": "https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/auth-v3/auth/tenant_access_token_internal",
    "authorization_code_guide": "https://open.feishu.cn/document/authentication-management/access-token/obtain-oauth-code",
    "authorize_login_guide": "https://open.feishu.cn/document/server-docs/authentication-management/login-state-management/authorize",
    "user_access_token": "https://open.feishu.cn/document/authentication-management/access-token/get-user-access-token",
    "user_access_token_oidc_legacy": "https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/oidc-access_token/create",
    "refresh_user_access_token_oidc": "https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/oidc-refresh_access_token/create",
}

OFFICIAL_REFERENCES = {
    "create_document": "https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document/create",
    "get_document": "https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document/get",
    "get_raw_content": "https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document/raw_content",
    "list_document_blocks": "https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/list",
    "convert_markdown_html": "https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document/convert",
    "create_blocks": "https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document-block-children/create",
    "create_descendant_blocks": "https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document-block-descendant/create",
    "delete_block_children": "https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block/batch_delete",
    "create_folder": "https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/file/create_folder",
    "root_folder_meta": "https://open.feishu.cn/document/server-docs/docs/drive-explorer-v2/root_folder/meta?lang=zh-CN",
    "list_drive_files": "https://open.feishu.cn/document/server-docs/docs/drive-v1/file/list?lang=zh-CN",
    "delete_file": "https://open.feishu.cn/document/server-docs/docs/drive-v1/file/delete?lang=zh-CN",
    "upload_media": "https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/media/upload_all",
}

DEFAULT_BASE_URL = "https://open.feishu.cn"
APP_ACCESS_TOKEN_ENDPOINT = "/open-apis/auth/v3/app_access_token/internal"
TENANT_TOKEN_ENDPOINT = "/open-apis/auth/v3/tenant_access_token/internal"
OIDC_AUTHORIZE_ENDPOINT = "/open-apis/authen/v1/authorize"
OAUTH_ACCESS_TOKEN_ENDPOINT = "/open-apis/authen/v2/oauth/token"
CREATE_DOCUMENT_ENDPOINT = "/open-apis/docx/v1/documents"
GET_DOCUMENT_ENDPOINT_TEMPLATE = "/open-apis/docx/v1/documents/{document_id}"
GET_DOCUMENT_RAW_CONTENT_ENDPOINT_TEMPLATE = "/open-apis/docx/v1/documents/{document_id}/raw_content"
LIST_DOCUMENT_BLOCKS_ENDPOINT_TEMPLATE = "/open-apis/docx/v1/documents/{document_id}/blocks"
CONVERT_DOCUMENT_BLOCKS_ENDPOINT = "/open-apis/docx/v1/documents/blocks/convert"
ROOT_FOLDER_META_ENDPOINT = "/open-apis/drive/explorer/v2/root_folder/meta"
LIST_DRIVE_FILES_ENDPOINT = "/open-apis/drive/v1/files"
CREATE_FOLDER_ENDPOINT = "/open-apis/drive/v1/files/create_folder"
UPLOAD_MEDIA_ENDPOINT = "/open-apis/drive/v1/medias/upload_all"
DELETE_DRIVE_FILE_ENDPOINT_TEMPLATE = "/open-apis/drive/v1/files/{file_token}"
CREATE_DESCENDANT_BLOCKS_ENDPOINT_TEMPLATE = "/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/descendant"
DELETE_BLOCK_CHILDREN_ENDPOINT_TEMPLATE = (
    "/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children/batch_delete"
)


def print_json(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=False))


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_reference_list(*values: Any) -> List[str]:
    result: List[str] = []
    for value in values:
        if not value:
            continue
        items = [value] if isinstance(value, str) else list(value)
        for item in items:
            if isinstance(item, str) and item and item not in result:
                result.append(item)
    return result


def build_command_response(
    command: str,
    ok: bool,
    *,
    mode: Optional[str] = None,
    base_url: Optional[str] = None,
    token_source: Optional[str] = None,
    official_docs: Optional[Any] = None,
    request: Optional[Any] = None,
    auth: Optional[Any] = None,
    result: Optional[Any] = None,
    error: Optional[str] = None,
    notes: Optional[List[str]] = None,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "ok": bool(ok),
        "command": command,
    }
    if mode is not None:
        response["mode"] = mode
    if base_url is not None:
        response["base_url"] = base_url
    if token_source is not None:
        response["token_source"] = token_source
    doc_refs = normalize_reference_list(official_docs)
    if doc_refs:
        response["official_docs"] = doc_refs
    if request is not None:
        response["request"] = request
    if auth is not None:
        response["auth"] = auth
    if result is not None:
        response["result"] = result
    if error is not None:
        response["error"] = error
    if notes:
        response["notes"] = notes
    if extras:
        for key, value in extras.items():
            if value is not None:
                response[key] = value
    return response


def summarize_tenant_auth(token_result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": bool(token_result.get("ok")),
        "status": token_result.get("status"),
        "code": token_result.get("code"),
        "msg": token_result.get("msg"),
        "expire": token_result.get("expire"),
        "tenant_access_token_preview": token_result.get("tenant_access_token_preview"),
    }


def normalize_base_url(base_url: Optional[str]) -> str:
    return (base_url or os.getenv("FEISHU_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def get_request_timeout(args: argparse.Namespace, default: int = 20) -> int:
    value = getattr(args, "request_timeout", None)
    if value is not None:
        return int(value)
    value = getattr(args, "timeout", None)
    if value is not None:
        return int(value)
    return default


def mask_secret(value: str) -> str:
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 6) + value[-3:]


def preview_token(value: str) -> str:
    if len(value) <= 10:
        return mask_secret(value)
    return value[:6] + "..." + value[-4:]


def redact_sensitive_payload(payload: Any) -> Any:
    sensitive_keys = {
        "access_token",
        "app_access_token",
        "tenant_access_token",
        "user_access_token",
        "refresh_token",
        "id_token",
        "code",
    }
    if isinstance(payload, dict):
        redacted: Dict[str, Any] = {}
        for key, value in payload.items():
            if key in sensitive_keys and isinstance(value, str):
                redacted[key] = preview_token(value)
            else:
                redacted[key] = redact_sensitive_payload(value)
        return redacted
    if isinstance(payload, list):
        return [redact_sensitive_payload(item) for item in payload]
    return payload


def resolve_required_value(args: argparse.Namespace, arg_name: str, env_name: str) -> str:
    value = getattr(args, arg_name, None) or os.getenv(env_name)
    if value:
        return value
    raise ValueError(f"Missing required value: use --{arg_name.replace('_', '-')} or set {env_name}")


def resolve_required_arg_or_env(
    args: argparse.Namespace,
    arg_name: str,
    env_name: str,
    display_name: Optional[str] = None,
) -> str:
    value = getattr(args, arg_name, None) or os.getenv(env_name)
    if value:
        return str(value)
    target = display_name or f"--{arg_name.replace('_', '-')}"
    raise ValueError(f"Missing required value: use {target} or set {env_name}")


def parse_json_payload(raw_text: str) -> Any:
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text


def request_json(
    method: str,
    url: str,
    timeout: int,
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    request_headers = dict(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json; charset=utf-8")

    request = urllib_request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", "replace")
            return {
                "ok": True,
                "status": response.status,
                "payload": parse_json_payload(raw_text),
                "raw_text": raw_text,
            }
    except urllib_error.HTTPError as exc:
        raw_text = exc.read().decode("utf-8", "replace")
        return {
            "ok": False,
            "status": exc.code,
            "payload": parse_json_payload(raw_text),
            "raw_text": raw_text,
        }
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Network error while calling {url}: {exc}") from exc


def encode_multipart_form_data(
    fields: Dict[str, str],
    files: List[Tuple[str, str, bytes, Optional[str]]],
) -> Tuple[bytes, str]:
    boundary = "----CodexFeishu" + uuid.uuid4().hex
    body_parts: List[bytes] = []

    for name, value in fields.items():
        body_parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    for field_name, filename, content, content_type in files:
        resolved_content_type = content_type or "application/octet-stream"
        body_parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {resolved_content_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
            ]
        )

    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(body_parts), f"multipart/form-data; boundary={boundary}"


def request_multipart(
    method: str,
    url: str,
    timeout: int,
    headers: Optional[Dict[str, str]] = None,
    fields: Optional[Dict[str, str]] = None,
    files: Optional[List[Tuple[str, str, bytes, Optional[str]]]] = None,
) -> Dict[str, Any]:
    request_headers = dict(headers or {})
    body, content_type = encode_multipart_form_data(fields or {}, files or [])
    request_headers["Content-Type"] = content_type

    request = urllib_request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", "replace")
            return {
                "ok": True,
                "status": response.status,
                "payload": parse_json_payload(raw_text),
                "raw_text": raw_text,
            }
    except urllib_error.HTTPError as exc:
        raw_text = exc.read().decode("utf-8", "replace")
        return {
            "ok": False,
            "status": exc.code,
            "payload": parse_json_payload(raw_text),
            "raw_text": raw_text,
        }
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Network error while calling {url}: {exc}") from exc


def parse_feishu_success(response: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[str]]:
    payload = response.get("payload")
    if not isinstance(payload, dict):
        return False, None, "Response is not JSON."
    return payload.get("code") == 0, payload.get("code"), payload.get("msg")


def extract_document_info(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    data = payload.get("data", {})
    if not isinstance(data, dict):
        return {}

    document = data.get("document")
    if isinstance(document, dict):
        return document

    return data


def extract_payload_data(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
    return {}


def extract_token_bundle(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    data = payload.get("data")
    if isinstance(data, dict) and any(
        key in data for key in ("access_token", "refresh_token", "user_access_token", "id_token")
    ):
        return data

    if any(
        key in payload for key in ("access_token", "refresh_token", "user_access_token", "id_token")
    ):
        return payload

    return {}


def parse_user_oauth_success(response: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[str], Dict[str, Any]]:
    payload = response.get("payload")
    if not isinstance(payload, dict):
        return False, None, "Response is not JSON.", {}

    bundle = extract_token_bundle(payload)
    code = payload.get("code")
    message = payload.get("message") or payload.get("msg")

    if not message:
        error_code = payload.get("error")
        error_description = payload.get("error_description")
        if error_code and error_description:
            message = f"{error_code}: {error_description}"
        elif error_code:
            message = str(error_code)
        elif error_description:
            message = str(error_description)

    if response["ok"] and bundle:
        return True, code, message, bundle

    return False, code, message, bundle


def fetch_tenant_access_token(
    app_id: str,
    app_secret: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    response = request_json(
        "POST",
        base_url + TENANT_TOKEN_ENDPOINT,
        timeout=timeout,
        payload={"app_id": app_id, "app_secret": app_secret},
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    if not response["ok"] or not success or not isinstance(payload, dict) or "tenant_access_token" not in payload:
        return {
            "ok": False,
            "status": response.get("status"),
            "code": code,
            "msg": msg or "Failed to obtain tenant_access_token.",
            "payload": payload,
        }

    tenant_access_token = str(payload["tenant_access_token"])
    app_access_token = payload.get("app_access_token")
    expire = payload.get("expire")
    return {
        "ok": True,
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "tenant_access_token": tenant_access_token,
        "tenant_access_token_preview": preview_token(tenant_access_token),
        "app_access_token_preview": preview_token(str(app_access_token)) if app_access_token else None,
        "expire": expire,
    }


def fetch_app_access_token(
    app_id: str,
    app_secret: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    response = request_json(
        "POST",
        base_url + APP_ACCESS_TOKEN_ENDPOINT,
        timeout=timeout,
        payload={"app_id": app_id, "app_secret": app_secret},
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    if not response["ok"] or not success or not isinstance(payload, dict) or "app_access_token" not in payload:
        return {
            "ok": False,
            "status": response.get("status"),
            "code": code,
            "msg": msg or "Failed to obtain app_access_token.",
            "payload": payload,
        }

    app_access_token = str(payload["app_access_token"])
    expire = payload.get("expire")
    return {
        "ok": True,
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "app_access_token": app_access_token,
        "app_access_token_preview": preview_token(app_access_token),
        "expire": expire,
    }


def resolve_tenant_token(args: argparse.Namespace) -> Dict[str, Any]:
    env_token = os.getenv("FEISHU_TENANT_ACCESS_TOKEN")
    if env_token and not getattr(args, "force_refresh", False):
        return {
            "ok": True,
            "source": "env",
            "tenant_access_token": env_token,
            "tenant_access_token_preview": preview_token(env_token),
            "expire": None,
            "app_access_token_preview": None,
            "status": None,
            "code": 0,
            "msg": "Using FEISHU_TENANT_ACCESS_TOKEN from the environment.",
        }

    app_id = resolve_required_value(args, "app_id", "FEISHU_APP_ID")
    app_secret = resolve_required_value(args, "app_secret", "FEISHU_APP_SECRET")
    token_result = fetch_tenant_access_token(
        app_id=app_id,
        app_secret=app_secret,
        base_url=normalize_base_url(args.base_url),
        timeout=get_request_timeout(args),
    )
    token_result["source"] = "fetched"
    token_result["app_id"] = app_id
    return token_result


def resolve_app_access_token(args: argparse.Namespace) -> Dict[str, Any]:
    env_token = os.getenv("FEISHU_APP_ACCESS_TOKEN")
    if env_token and not getattr(args, "force_refresh", False):
        return {
            "ok": True,
            "source": "env",
            "app_access_token": env_token,
            "app_access_token_preview": preview_token(env_token),
            "expire": None,
            "status": None,
            "code": 0,
            "msg": "Using FEISHU_APP_ACCESS_TOKEN from the environment.",
        }

    app_id = resolve_required_value(args, "app_id", "FEISHU_APP_ID")
    app_secret = resolve_required_value(args, "app_secret", "FEISHU_APP_SECRET")
    token_result = fetch_app_access_token(
        app_id=app_id,
        app_secret=app_secret,
        base_url=normalize_base_url(args.base_url),
        timeout=get_request_timeout(args),
    )
    token_result["source"] = "fetched"
    token_result["app_id"] = app_id
    return token_result


def build_user_auth_url(
    app_id: str,
    redirect_uri: str,
    base_url: str,
    state: str,
    scope: Optional[str] = None,
) -> str:
    query: Dict[str, str] = {
        "app_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    if scope:
        query["scope"] = scope
    return base_url + OIDC_AUTHORIZE_ENDPOINT + "?" + urllib_parse.urlencode(query)


def normalize_callback_path(path: str) -> str:
    value = path.strip() or "/callback"
    if not value.startswith("/"):
        value = "/" + value
    return value


def build_local_redirect_uri(host: str, port: int, callback_path: str) -> str:
    return f"http://{host}:{port}{normalize_callback_path(callback_path)}"


class LocalOAuthCallbackResult:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.query: Dict[str, str] = {}
        self.path = ""


class LocalOAuthCallbackServer(ThreadingHTTPServer):
    callback_path: str
    callback_result: LocalOAuthCallbackResult
    success_html: bytes
    failure_html: bytes


class LocalOAuthCallbackHandler(BaseHTTPRequestHandler):
    server: LocalOAuthCallbackServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib_parse.urlparse(self.path)
        if parsed.path != self.server.callback_path:
            body = self.server.failure_html
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        query = urllib_parse.parse_qs(parsed.query)
        self.server.callback_result.query = {
            key: values[0] for key, values in query.items() if values
        }
        self.server.callback_result.path = parsed.path
        self.server.callback_result.event.set()

        body = self.server.success_html
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_callback_html(title: str, message: str) -> bytes:
    safe_title = html.escape(title, quote=True)
    safe_message = html.escape(message, quote=True)
    html_text = (
        "<!doctype html>"
        "<html><head><meta charset='utf-8'>"
        f"<title>{safe_title}</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;background:#f7f8fa;color:#112233;"
        "display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}"
        ".card{max-width:520px;background:white;border:1px solid #dde3ea;border-radius:12px;"
        "padding:24px;box-shadow:0 10px 30px rgba(17,34,51,.08);}"
        "h1{font-size:20px;margin:0 0 12px;}p{line-height:1.5;margin:0;}"
        "</style></head><body><div class='card'>"
        f"<h1>{safe_title}</h1><p>{safe_message}</p>"
        "</div></body></html>"
    )
    return html_text.encode("utf-8")


def start_local_oauth_callback_server(
    host: str,
    port: int,
    callback_path: str,
) -> Tuple[LocalOAuthCallbackServer, LocalOAuthCallbackResult]:
    callback_result = LocalOAuthCallbackResult()
    server = LocalOAuthCallbackServer((host, port), LocalOAuthCallbackHandler)
    server.callback_path = normalize_callback_path(callback_path)
    server.callback_result = callback_result
    server.success_html = build_callback_html(
        "Feishu Authorization Received",
        "The authorization callback was received. You can close this window now.",
    )
    server.failure_html = build_callback_html(
        "Invalid Callback Path",
        "This local callback server only accepts the configured authorization path.",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, callback_result


def exchange_user_access_token(
    app_id: str,
    app_secret: str,
    code: str,
    redirect_uri: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    response = request_json(
        "POST",
        base_url + OAUTH_ACCESS_TOKEN_ENDPOINT,
        timeout=timeout,
        payload={
            "grant_type": "authorization_code",
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    success, code_value, message, bundle = parse_user_oauth_success(response)
    payload = response.get("payload")
    result: Dict[str, Any] = {
        "kind": "oauth_v2_exchange_user_access_token",
        "ok": success,
        "status": response.get("status"),
        "code": code_value,
        "message": message,
        "token_bundle": bundle,
    }
    if not success:
        result["payload"] = payload
    return result


def probe_document_connectivity(
    tenant_access_token: str,
    document_id: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    url = base_url + GET_DOCUMENT_ENDPOINT_TEMPLATE.format(
        document_id=urllib_parse.quote(document_id, safe="")
    )
    response = request_json(
        "GET",
        url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    document = extract_document_info(payload)

    result: Dict[str, Any] = {
        "kind": "docx_get_document",
        "document_id": document_id,
        "ok": bool(response["ok"] and success),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "title": document.get("title"),
        "revision_id": document.get("revision_id"),
    }

    if "document_id" in document:
        result["resolved_document_id"] = document.get("document_id")

    if not result["ok"]:
        result["payload"] = payload

    return result


def get_document_raw_content(
    tenant_access_token: str,
    document_id: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    url = base_url + GET_DOCUMENT_RAW_CONTENT_ENDPOINT_TEMPLATE.format(
        document_id=urllib_parse.quote(document_id, safe="")
    )
    response = request_json(
        "GET",
        url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    data = extract_payload_data(payload)
    content = data.get("content")

    result: Dict[str, Any] = {
        "kind": "docx_get_raw_content",
        "document_id": document_id,
        "ok": bool(response["ok"] and success and isinstance(content, str)),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "content": content if isinstance(content, str) else None,
        "content_length": len(content) if isinstance(content, str) else 0,
        "content_hash": sha256_text(content) if isinstance(content, str) else None,
    }

    if not result["ok"]:
        result["payload"] = payload

    return result


def list_document_blocks(
    tenant_access_token: str,
    document_id: str,
    base_url: str,
    timeout: int,
    page_size: int = 500,
    page_token: Optional[str] = None,
    document_revision_id: int = -1,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {
        "page_size": page_size,
        "document_revision_id": document_revision_id,
    }
    if page_token:
        query["page_token"] = page_token

    url = base_url + LIST_DOCUMENT_BLOCKS_ENDPOINT_TEMPLATE.format(
        document_id=urllib_parse.quote(document_id, safe="")
    )
    if query:
        url += "?" + urllib_parse.urlencode(query)

    response = request_json(
        "GET",
        url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    data = extract_payload_data(payload)
    raw_items = data.get("items", [])
    items = raw_items if isinstance(raw_items, list) else []

    result: Dict[str, Any] = {
        "kind": "docx_list_document_blocks",
        "document_id": document_id,
        "ok": bool(response["ok"] and success and isinstance(items, list)),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "page_size": page_size,
        "page_token": page_token,
        "document_revision_id": document_revision_id,
        "count": len(items),
        "items": items,
        "has_more": bool(data.get("has_more")),
        "next_page_token": data.get("page_token") or data.get("next_page_token"),
    }

    if not result["ok"]:
        result["payload"] = payload

    return result


def delete_block_children(
    tenant_access_token: str,
    document_id: str,
    block_id: str,
    start_index: int,
    end_index: int,
    base_url: str,
    timeout: int,
    document_revision_id: int = -1,
    client_token: Optional[str] = None,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {"document_revision_id": document_revision_id}
    if client_token:
        query["client_token"] = client_token
    url = base_url + DELETE_BLOCK_CHILDREN_ENDPOINT_TEMPLATE.format(
        document_id=urllib_parse.quote(document_id, safe=""),
        block_id=urllib_parse.quote(block_id, safe=""),
    )
    if query:
        url += "?" + urllib_parse.urlencode(query)

    response = request_json(
        "DELETE",
        url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        payload={
            "start_index": start_index,
            "end_index": end_index,
        },
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    data = extract_payload_data(payload)

    result: Dict[str, Any] = {
        "kind": "docx_delete_block_children",
        "document_id": document_id,
        "block_id": block_id,
        "ok": bool(response["ok"] and success),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "start_index": start_index,
        "end_index": end_index,
        "deleted_count": max(0, end_index - start_index),
        "document_revision_id": data.get("document_revision_id"),
        "client_token": data.get("client_token"),
    }

    if not result["ok"]:
        result["payload"] = payload

    return result


def create_document(
    tenant_access_token: str,
    title: str,
    base_url: str,
    timeout: int,
    folder_token: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"title": title}
    if folder_token:
        payload["folder_token"] = folder_token

    response = request_json(
        "POST",
        base_url + CREATE_DOCUMENT_ENDPOINT,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        payload=payload,
    )
    raw_payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    document = extract_document_info(raw_payload)

    result: Dict[str, Any] = {
        "kind": "docx_create_document",
        "ok": bool(response["ok"] and success),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "title": document.get("title"),
        "revision_id": document.get("revision_id"),
        "document_id": document.get("document_id"),
        "url": document.get("url"),
    }

    if not result["ok"]:
        result["payload"] = raw_payload

    return result


def get_root_folder_meta(
    tenant_access_token: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    response = request_json(
        "GET",
        base_url + ROOT_FOLDER_META_ENDPOINT,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    data = extract_payload_data(payload)

    result: Dict[str, Any] = {
        "kind": "drive_root_folder_meta",
        "ok": bool(response["ok"] and success),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "id": data.get("id"),
        "token": data.get("token"),
        "user_id": data.get("user_id"),
    }

    if not result["ok"]:
        result["payload"] = payload

    return result


def list_drive_files(
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    folder_token: Optional[str] = None,
    page_size: int = 100,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {"page_size": page_size}
    if folder_token:
        query["folder_token"] = folder_token
    if page_token:
        query["page_token"] = page_token

    url = base_url + LIST_DRIVE_FILES_ENDPOINT + "?" + urllib_parse.urlencode(query)
    response = request_json(
        "GET",
        url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    data = extract_payload_data(payload)
    raw_files = data.get("files", [])
    files: List[Dict[str, Any]] = []

    if isinstance(raw_files, list):
        for entry in raw_files:
            if not isinstance(entry, dict):
                continue
            files.append(
                {
                    "name": entry.get("name"),
                    "type": entry.get("type"),
                    "token": entry.get("token"),
                    "parent_token": entry.get("parent_token"),
                    "url": entry.get("url"),
                    "created_time": entry.get("created_time"),
                    "modified_time": entry.get("modified_time"),
                }
            )

    result: Dict[str, Any] = {
        "kind": "drive_list_files",
        "ok": bool(response["ok"] and success),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "folder_token": folder_token,
        "page_size": page_size,
        "page_token": page_token,
        "has_more": bool(data.get("has_more")),
        "next_page_token": data.get("next_page_token"),
        "count": len(files),
        "files": files,
    }

    if not result["ok"]:
        result["payload"] = payload

    return result


def create_drive_folder(
    tenant_access_token: str,
    name: str,
    parent_folder_token: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    response = request_json(
        "POST",
        base_url + CREATE_FOLDER_ENDPOINT,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        payload={
            "name": name,
            "folder_token": parent_folder_token,
        },
    )
    raw_payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    data = extract_payload_data(raw_payload)
    folder_payload = data.get("folder") if isinstance(data.get("folder"), dict) else data
    token = None
    if isinstance(folder_payload, dict):
        token = (
            folder_payload.get("token")
            or folder_payload.get("file_token")
            or folder_payload.get("folder_token")
        )

    result: Dict[str, Any] = {
        "kind": "drive_create_folder",
        "ok": bool(response["ok"] and success and isinstance(token, str) and token),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "name": folder_payload.get("name") if isinstance(folder_payload, dict) else name,
        "token": str(token) if token else None,
        "parent_folder_token": parent_folder_token,
        "type": folder_payload.get("type") if isinstance(folder_payload, dict) else "folder",
        "url": folder_payload.get("url") if isinstance(folder_payload, dict) else None,
    }

    if not result["ok"]:
        result["payload"] = raw_payload

    return result


def delete_drive_file(
    tenant_access_token: str,
    file_token: str,
    file_type: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    query = urllib_parse.urlencode({"type": file_type})
    url = (
        base_url
        + DELETE_DRIVE_FILE_ENDPOINT_TEMPLATE.format(file_token=urllib_parse.quote(file_token, safe=""))
        + "?"
        + query
    )
    response = request_json(
        "DELETE",
        url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)

    result: Dict[str, Any] = {
        "kind": "drive_delete_file",
        "file_token": file_token,
        "file_type": file_type,
        "ok": bool(response["ok"] and success),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
    }

    if not result["ok"]:
        result["payload"] = payload

    return result


def fetch_all_document_blocks(
    tenant_access_token: str,
    document_id: str,
    base_url: str,
    timeout: int,
    page_size: int = 500,
    max_pages: int = 20,
    document_revision_id: int = -1,
) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    pages: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    page_count = 0

    while True:
        if page_count >= max_pages:
            return {
                "kind": "docx_fetch_all_blocks",
                "document_id": document_id,
                "ok": False,
                "page_count": page_count,
                "count": len(items),
                "items": items,
                "pages": pages,
                "error": f"Exceeded max_pages={max_pages} while listing document blocks.",
            }

        page_result = list_document_blocks(
            tenant_access_token=tenant_access_token,
            document_id=document_id,
            base_url=base_url,
            timeout=timeout,
            page_size=page_size,
            page_token=page_token,
            document_revision_id=document_revision_id,
        )
        page_count += 1
        pages.append(
            {
                "page": page_count,
                "ok": page_result.get("ok"),
                "status": page_result.get("status"),
                "code": page_result.get("code"),
                "msg": page_result.get("msg"),
                "count": page_result.get("count"),
                "has_more": page_result.get("has_more"),
                "next_page_token": page_result.get("next_page_token"),
            }
        )
        if not page_result.get("ok"):
            return {
                "kind": "docx_fetch_all_blocks",
                "document_id": document_id,
                "ok": False,
                "page_count": page_count,
                "count": len(items),
                "items": items,
                "pages": pages,
                "page_result": page_result,
                "error": "Failed to fetch the full document block tree.",
            }

        for item in page_result.get("items", []):
            if isinstance(item, dict):
                items.append(item)

        if not page_result.get("has_more"):
            break
        page_token = page_result.get("next_page_token")
        if not page_token:
            break

    return {
        "kind": "docx_fetch_all_blocks",
        "document_id": document_id,
        "ok": True,
        "page_count": page_count,
        "count": len(items),
        "items": items,
        "pages": pages,
    }


def render_markdown_text(text: str, style: Optional[Dict[str, Any]] = None) -> str:
    rendered = text or ""
    style = style if isinstance(style, dict) else {}
    if style.get("inline_code"):
        backticks = "``" if "`" in rendered else "`"
        rendered = f"{backticks}{rendered}{backticks}"
    if style.get("bold"):
        rendered = f"**{rendered}**"
    if style.get("italic"):
        rendered = f"*{rendered}*"
    if style.get("strikethrough"):
        rendered = f"~~{rendered}~~"
    if style.get("underline"):
        rendered = f"<u>{rendered}</u>"
    link = style.get("link")
    if isinstance(link, dict):
        href = link.get("url") or link.get("href")
        if isinstance(href, str) and href:
            rendered = f"[{rendered}]({href})"
    return rendered


def render_text_elements(elements: Any) -> str:
    if not isinstance(elements, list):
        return ""

    rendered_parts: List[str] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        text_run = element.get("text_run")
        if isinstance(text_run, dict):
            rendered_parts.append(
                render_markdown_text(
                    str(text_run.get("content") or ""),
                    text_run.get("text_element_style"),
                )
            )
            continue
        mention_user = element.get("mention_user")
        if isinstance(mention_user, dict):
            rendered_parts.append("@" + str(mention_user.get("name") or mention_user.get("user_id") or "user"))
            continue
        mention_doc = element.get("mention_doc")
        if isinstance(mention_doc, dict):
            title = str(mention_doc.get("title") or mention_doc.get("token") or "document")
            token = str(mention_doc.get("token") or "")
            rendered_parts.append(f"[{title}](feishu-doc:{token})" if token else title)
            continue
        reminder = element.get("reminder")
        if isinstance(reminder, dict):
            rendered_parts.append("@" + str(reminder.get("title") or "reminder"))
            continue
        equation = element.get("equation")
        if isinstance(equation, dict):
            rendered_parts.append("$" + str(equation.get("content") or "") + "$")
            continue
        if element.get("text") is not None:
            rendered_parts.append(str(element.get("text") or ""))
            continue
        rendered_parts.append(str(element))

    return "".join(rendered_parts).strip()


def extract_block_payload(block: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    for key in (
        "page",
        "text",
        "heading1",
        "heading2",
        "heading3",
        "heading4",
        "heading5",
        "heading6",
        "heading7",
        "heading8",
        "heading9",
        "bullet",
        "ordered",
        "quote",
        "code",
        "callout",
        "todo",
        "image",
        "file",
        "divider",
        "table",
    ):
        value = block.get(key)
        if isinstance(value, dict):
            return key, value
    return None, {}


def render_high_fidelity_markdown(
    document_id: str,
    document_title: str,
    block_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    block_map: Dict[str, Dict[str, Any]] = {}
    for item in block_items:
        if not isinstance(item, dict):
            continue
        block_id = item.get("block_id")
        if isinstance(block_id, str) and block_id:
            block_map[block_id] = item

    root_block = block_map.get(document_id)
    if root_block is None:
        for item in block_items:
            if isinstance(item, dict) and str(item.get("block_type")) == "1":
                root_block = item
                break
    if root_block is None:
        return {
            "ok": False,
            "error": "Could not resolve the root page block for high-fidelity export.",
            "unsupported_block_count": 0,
        }

    page_key, page_payload = extract_block_payload(root_block)
    rendered_title = render_text_elements(page_payload.get("elements")) if page_key == "page" else ""
    title = rendered_title or document_title or document_id
    unsupported_blocks: List[Dict[str, Any]] = []
    visited: set[str] = set()

    def render_child_block(block_id: str, depth: int = 0) -> List[str]:
        if block_id in visited:
            return [f"<!-- cycle detected for block {block_id} -->"]
        visited.add(block_id)
        block = block_map.get(block_id)
        if block is None:
            return [f"<!-- missing block {block_id} -->"]

        payload_key, payload = extract_block_payload(block)
        children = [
            str(child_id)
            for child_id in block.get("children", [])
            if isinstance(child_id, str) and child_id
        ]

        if payload_key == "text":
            text = render_text_elements(payload.get("elements"))
            return [text or ""]
        if payload_key and payload_key.startswith("heading"):
            level_text = payload_key.replace("heading", "")
            level = int(level_text) if level_text.isdigit() else 1
            text = render_text_elements(payload.get("elements")) or title
            return [("#" * min(level, 6)) + " " + text]
        if payload_key == "bullet":
            text = render_text_elements(payload.get("elements")) or "-"
            lines = [("  " * depth) + "- " + text]
            for child_id in children:
                lines.extend(render_child_block(child_id, depth + 1))
            return lines
        if payload_key == "ordered":
            text = render_text_elements(payload.get("elements")) or "item"
            lines = [("  " * depth) + "1. " + text]
            for child_id in children:
                lines.extend(render_child_block(child_id, depth + 1))
            return lines
        if payload_key == "quote":
            text = render_text_elements(payload.get("elements"))
            lines = ["> " + line if line else ">" for line in (text.splitlines() or [""])]
            for child_id in children:
                lines.extend(["> " + line if line else ">" for line in render_child_block(child_id, depth)])
            return lines
        if payload_key == "code":
            language = str(payload.get("language") or payload.get("lang") or "").strip()
            text = render_text_elements(payload.get("elements")) or str(payload.get("content") or "")
            return [f"```{language}".rstrip(), text, "```"]
        if payload_key == "todo":
            text = render_text_elements(payload.get("elements")) or "todo"
            done = bool(payload.get("is_checked") or payload.get("checked"))
            marker = "x" if done else " "
            return [("  " * depth) + f"- [{marker}] " + text]
        if payload_key == "image":
            token = str(payload.get("token") or payload.get("file_token") or "")
            alt = str(payload.get("title") or payload.get("alt") or "image")
            url = str(payload.get("url") or "")
            target = url or (f"feishu-media:{token}" if token else "feishu-media")
            return [f"![{alt}]({target})"]
        if payload_key == "file":
            token = str(payload.get("token") or payload.get("file_token") or "")
            name = str(payload.get("file_name") or payload.get("name") or "attachment")
            return [f"[{name}](feishu-file:{token})" if token else f"[{name}]()"]
        if payload_key == "divider":
            return ["---"]
        if payload_key == "callout":
            text = render_text_elements(payload.get("elements")) or "callout"
            return ["> " + text]

        unsupported_blocks.append(
            {
                "block_id": block_id,
                "block_type": block.get("block_type"),
                "payload_key": payload_key,
            }
        )
        label = payload_key or f"block_type_{block.get('block_type')}"
        return [f"<!-- unsupported block: {label} ({block_id}) -->"]

    top_level_children = [
        str(child_id)
        for child_id in root_block.get("children", [])
        if isinstance(child_id, str) and child_id
    ]
    rendered_sections: List[str] = [f"# {title}"]
    for child_id in top_level_children:
        child_lines = render_child_block(child_id, 0)
        rendered_sections.append("\n".join(child_lines).rstrip())

    markdown = "\n\n".join(section for section in rendered_sections if section is not None and section != "").rstrip() + "\n"
    return {
        "ok": True,
        "title": title,
        "markdown": markdown,
        "unsupported_blocks": unsupported_blocks,
        "unsupported_block_count": len(unsupported_blocks),
        "block_count": len(block_map),
    }


def upload_document_media(
    tenant_access_token: str,
    document_id: str,
    file_path: Path,
    base_url: str,
    timeout: int,
    parent_type: str = "docx_image",
    file_name: Optional[str] = None,
    extra_drive_route_token: Optional[str] = None,
    checksum: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_path = file_path.resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Media file not found: {resolved_path}")

    file_bytes = resolved_path.read_bytes()
    resolved_file_name = file_name or resolved_path.name
    content_type = mimetypes.guess_type(resolved_file_name)[0] or "application/octet-stream"
    resolved_checksum = checksum or str(zlib.adler32(file_bytes) & 0xFFFFFFFF)
    fields = {
        "file_name": resolved_file_name,
        "parent_type": parent_type,
        "parent_node": document_id,
        "size": str(len(file_bytes)),
        "checksum": resolved_checksum,
    }
    if extra_drive_route_token:
        fields["extra"] = json.dumps({"drive_route_token": extra_drive_route_token}, ensure_ascii=False)

    response = request_multipart(
        "POST",
        base_url + UPLOAD_MEDIA_ENDPOINT,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        fields=fields,
        files=[("file", resolved_file_name, file_bytes, content_type)],
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    data = extract_payload_data(payload)
    file_token = data.get("file_token") if isinstance(data, dict) else None

    result: Dict[str, Any] = {
        "kind": "drive_upload_media",
        "ok": bool(response["ok"] and success and isinstance(file_token, str) and file_token),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "document_id": document_id,
        "parent_type": parent_type,
        "path": str(resolved_path),
        "file_name": resolved_file_name,
        "size": len(file_bytes),
        "checksum": resolved_checksum,
        "content_type": content_type,
        "file_token": str(file_token) if isinstance(file_token, str) else None,
    }
    if extra_drive_route_token:
        result["extra_drive_route_token"] = extra_drive_route_token

    if not result["ok"]:
        result["payload"] = payload

    return result


def strip_merge_info(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if key == "merge_info":
                continue
            cleaned[key] = strip_merge_info(item)
        return cleaned
    if isinstance(value, list):
        return [strip_merge_info(item) for item in value]
    return value


def convert_markdown_to_blocks(
    tenant_access_token: str,
    content: str,
    base_url: str,
    timeout: int,
    content_type: str = "markdown",
    user_id_type: Optional[str] = None,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {}
    if user_id_type:
        query["user_id_type"] = user_id_type
    url = base_url + CONVERT_DOCUMENT_BLOCKS_ENDPOINT
    if query:
        url += "?" + urllib_parse.urlencode(query)

    response = request_json(
        "POST",
        url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        payload={"content_type": content_type, "content": content},
    )
    payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    data = extract_payload_data(payload)
    raw_blocks = data.get("blocks", [])
    blocks = strip_merge_info(raw_blocks) if isinstance(raw_blocks, list) else []
    first_level_ids = data.get("first_level_block_ids", [])
    image_url_map = data.get("block_id_to_image_urls", {})

    result: Dict[str, Any] = {
        "kind": "docx_convert_markdown_to_blocks",
        "ok": bool(response["ok"] and success and isinstance(first_level_ids, list) and isinstance(blocks, list)),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "content_type": content_type,
        "first_level_block_ids": first_level_ids if isinstance(first_level_ids, list) else [],
        "first_level_count": len(first_level_ids) if isinstance(first_level_ids, list) else 0,
        "blocks": blocks,
        "block_count": len(blocks),
        "block_id_to_image_urls": image_url_map if isinstance(image_url_map, dict) else {},
    }

    if not result["ok"]:
        result["payload"] = payload

    return result


def create_descendant_blocks(
    tenant_access_token: str,
    document_id: str,
    block_id: str,
    children_ids: List[str],
    descendants: List[Dict[str, Any]],
    base_url: str,
    timeout: int,
    document_revision_id: int = -1,
    user_id_type: Optional[str] = None,
    index: Optional[int] = None,
    client_token: Optional[str] = None,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {"document_revision_id": document_revision_id}
    if client_token:
        query["client_token"] = client_token
    if user_id_type:
        query["user_id_type"] = user_id_type
    url = base_url + CREATE_DESCENDANT_BLOCKS_ENDPOINT_TEMPLATE.format(
        document_id=urllib_parse.quote(document_id, safe=""),
        block_id=urllib_parse.quote(block_id, safe=""),
    )
    if query:
        url += "?" + urllib_parse.urlencode(query)

    payload: Dict[str, Any] = {
        "children_id": children_ids,
        "descendants": descendants,
    }
    if index is not None:
        payload["index"] = index

    response = request_json(
        "POST",
        url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        payload=payload,
    )
    raw_payload = response.get("payload")
    success, code, msg = parse_feishu_success(response)
    data = extract_payload_data(raw_payload)

    relations = data.get("block_id_relations", [])
    children = data.get("children", [])
    result: Dict[str, Any] = {
        "kind": "docx_create_descendant_blocks",
        "ok": bool(response["ok"] and success),
        "status": response.get("status"),
        "code": code,
        "msg": msg,
        "document_revision_id": data.get("document_revision_id"),
        "client_token": data.get("client_token"),
        "relation_count": len(relations) if isinstance(relations, list) else 0,
        "child_count": len(children) if isinstance(children, list) else 0,
        "block_id_relations": relations if isinstance(relations, list) else [],
        "children": children if isinstance(children, list) else [],
    }

    if not result["ok"]:
        result["payload"] = raw_payload

    return result


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def encode_text_snapshot(text: str) -> Dict[str, Any]:
    raw_bytes = text.encode("utf-8")
    compressed = zlib.compress(raw_bytes, level=9)
    return {
        "encoding": "zlib+base64:utf-8",
        "data": base64.b64encode(compressed).decode("ascii"),
        "length": len(raw_bytes),
        "content_hash": sha256_text(text),
    }


def decode_text_snapshot(snapshot: Any) -> Optional[str]:
    if isinstance(snapshot, str):
        return snapshot
    if not isinstance(snapshot, dict):
        return None
    if str(snapshot.get("encoding") or "") != "zlib+base64:utf-8":
        return None
    encoded = snapshot.get("data")
    if not isinstance(encoded, str) or not encoded:
        return None
    try:
        compressed = base64.b64decode(encoded.encode("ascii"), validate=True)
        return zlib.decompress(compressed).decode("utf-8")
    except (ValueError, zlib.error, UnicodeDecodeError):
        return None


def extract_index_baseline_body(entry: Dict[str, Any]) -> Optional[str]:
    for key in ("baseline_body_snapshot", "last_sync_body_snapshot"):
        text = decode_text_snapshot(entry.get(key))
        if isinstance(text, str):
            return text
    legacy_text = entry.get("baseline_body")
    if isinstance(legacy_text, str) and legacy_text:
        return legacy_text
    return None


def split_front_matter(text: str) -> Tuple[Dict[str, Any], str, bool]:
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    if not text.startswith("---"):
        return {}, text, False

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, False

    front_matter_lines: List[str] = []
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "\n".join(lines[index + 1 :])
            return parse_simple_yaml(front_matter_lines), body, True
        front_matter_lines.append(line)

    return {}, text, False


def parse_simple_yaml(lines: List[str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in raw_line:
            continue

        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]

        low = value.lower()
        if low == "true":
            data[key] = True
        elif low == "false":
            data[key] = False
        elif low in {"null", "none"}:
            data[key] = None
        else:
            data[key] = value

    return data


def extract_title(front_matter: Dict[str, Any], body: str, path: Path) -> str:
    for key in ("title", "feishu_title"):
        value = front_matter.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    match = re.search(r"(?m)^\s*#\s+(.+?)\s*$", body)
    if match:
        return match.group(1).strip()

    return path.stem.replace("-", " ").replace("_", " ").strip() or path.name


def discover_index_path(start: Path) -> Optional[Path]:
    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        index_path = candidate / INDEX_FILENAME
        if index_path.is_file():
            return index_path
    return None


def load_index_payload(index_path: Optional[Path]) -> Dict[str, Any]:
    if not index_path or not index_path.is_file():
        return {"version": 1, "files": []}

    try:
        raw_payload = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "files": []}

    if isinstance(raw_payload, dict):
        files = raw_payload.get("files", [])
        payload = {key: value for key, value in raw_payload.items() if key != "files"}
    elif isinstance(raw_payload, list):
        files = raw_payload
        payload = {"version": 1}
    else:
        return {"version": 1, "files": []}

    normalized_files: List[Dict[str, Any]] = []
    if isinstance(files, list):
        for entry in files:
            if not isinstance(entry, dict):
                continue
            relative_path = entry.get("relative_path") or entry.get("path")
            if isinstance(relative_path, str) and relative_path:
                normalized = dict(entry)
                normalized["relative_path"] = relative_path.replace("\\", "/")
                normalized_files.append(normalized)

    payload["version"] = payload.get("version") or 1
    payload["files"] = normalized_files
    return payload


def load_index(index_path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for entry in load_index_payload(index_path).get("files", []):
        relative_path = entry.get("relative_path")
        if isinstance(relative_path, str) and relative_path:
            result[relative_path] = entry
    return result


def resolve_index_path(root: Path, explicit_index_path: Optional[str] = None) -> Path:
    if explicit_index_path:
        return Path(explicit_index_path).resolve()
    discovered = discover_index_path(root)
    if discovered:
        return discovered.resolve()
    return (root / INDEX_FILENAME).resolve()


def write_index_payload(index_path: Path, payload: Dict[str, Any]) -> None:
    normalized_payload = dict(payload)
    files = normalized_payload.get("files", [])
    normalized_files = []
    if isinstance(files, list):
        normalized_files = sorted(
            [entry for entry in files if isinstance(entry, dict)],
            key=lambda entry: str(entry.get("relative_path", "")),
        )
    normalized_payload["version"] = normalized_payload.get("version") or 1
    normalized_payload["files"] = normalized_files
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(normalized_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def update_index_entry(index_path: Path, relative_path: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    payload = load_index_payload(index_path)
    entries = {
        str(entry.get("relative_path")): dict(entry)
        for entry in payload.get("files", [])
        if isinstance(entry, dict) and entry.get("relative_path")
    }
    entry = dict(entries.get(relative_path, {}))
    entry["relative_path"] = relative_path
    for key, value in updates.items():
        if value is None:
            continue
        entry[key] = value
    entries[relative_path] = entry
    payload["files"] = list(entries.values())
    write_index_payload(index_path, payload)
    return entry


def remove_index_entries(index_path: Path, relative_paths: List[str]) -> Dict[str, Any]:
    normalized_targets = {
        str(relative_path).replace("\\", "/").strip("/")
        for relative_path in relative_paths
        if str(relative_path).strip()
    }
    payload = load_index_payload(index_path)
    entries = []
    removed: List[Dict[str, Any]] = []
    for entry in payload.get("files", []):
        if not isinstance(entry, dict):
            continue
        relative_path = str(entry.get("relative_path") or "").replace("\\", "/").strip("/")
        if relative_path and relative_path in normalized_targets:
            removed.append(dict(entry))
            continue
        entries.append(entry)
    payload["files"] = entries
    write_index_payload(index_path, payload)
    return {
        "removed_count": len(removed),
        "removed_entries": removed,
    }


def current_timestamp_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_slug_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")


def resolve_sync_backup_run_dir(
    root: Path,
    backup_dir: Optional[str],
    prefix: str = "sync-dir-prune",
) -> Path:
    base_dir = Path(backup_dir).resolve() if backup_dir else (root / SYNC_BACKUP_DIRNAME).resolve()
    timestamp = timestamp_slug_utc()
    candidate = base_dir / f"{prefix}-{timestamp}"
    suffix = 1
    while candidate.exists():
        candidate = base_dir / f"{prefix}-{timestamp}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def normalize_relative_dir(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip().strip("/")
    if text in ("", "."):
        return ""
    return text


def is_drive_folder_type(file_type: Any) -> bool:
    return isinstance(file_type, str) and file_type.strip().lower() == "folder"


def is_drive_docx_type(file_type: Any) -> bool:
    return isinstance(file_type, str) and file_type.strip().lower() == "docx"


def sanitize_path_component(value: Any, fallback: str = "untitled") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"[<>:\"/\\\\|?*\x00-\x1f]+", "-", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("- .")
    return text or fallback


def ensure_markdown_extension(name: str) -> str:
    return name if name.lower().endswith(".md") else f"{name}.md"


def render_front_matter_value(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    return str(value)


def render_front_matter_block(values: Dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        if value in (None, ""):
            continue
        lines.append(f"{key}: {render_front_matter_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def compose_low_fidelity_markdown(
    title: str,
    document_id: str,
    raw_content: str,
    sync_direction: str,
) -> str:
    normalized_title = title.strip() or document_id
    stripped_raw = raw_content.strip()
    first_line = first_nonempty_line(stripped_raw)
    if stripped_raw:
        if first_line == normalized_title:
            body = stripped_raw
        else:
            body = f"# {normalized_title}\n\n{stripped_raw}"
    else:
        body = f"# {normalized_title}"

    return compose_exported_markdown(
        title=normalized_title,
        document_id=document_id,
        body_markdown=body,
        sync_direction=sync_direction,
        fidelity="raw_content",
    )


def compose_exported_markdown(
    title: str,
    document_id: str,
    body_markdown: str,
    sync_direction: str,
    fidelity: str,
) -> str:
    normalized_title = title.strip() or document_id
    front_matter = render_front_matter_block(
        {
            "title": normalized_title,
            "feishu_doc_token": document_id,
            "feishu_sync_direction": sync_direction,
            "feishu_pull_fidelity": fidelity,
        }
    )
    return front_matter + "\n\n" + body_markdown.rstrip() + "\n"


def load_local_diff_body(plan: Dict[str, Any]) -> Dict[str, Any]:
    path_value = plan.get("path")
    resolved_path = Path(str(path_value or "")).resolve()
    if not resolved_path.is_file():
        return {
            "ok": False,
            "path": str(resolved_path),
            "error": "The local Markdown file is no longer readable, so sync-dir could not build a local diff preview.",
        }

    front_matter, body, has_front_matter, title = read_markdown_file(resolved_path)
    return {
        "ok": True,
        "path": str(resolved_path),
        "title": title,
        "has_front_matter": has_front_matter,
        "front_matter_keys": sorted(front_matter.keys()),
        "body_markdown": body,
        "body_hash": sha256_text(body),
    }


def build_remote_diff_body(
    document_id: str,
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    metadata_result: Dict[str, Any],
    raw_result: Dict[str, Any],
    fidelity: str = "low",
    title_override: Optional[str] = None,
) -> Dict[str, Any]:
    title = str(title_override or metadata_result.get("title") or document_id).strip() or document_id
    raw_content = str(raw_result.get("content") or "")
    degradation_note: Optional[str] = None

    if fidelity == "high":
        block_result = fetch_all_document_blocks(
            tenant_access_token=tenant_access_token,
            document_id=document_id,
            base_url=base_url,
            timeout=timeout,
        )
        if block_result.get("ok"):
            rendered_result = render_high_fidelity_markdown(
                document_id=document_id,
                document_title=title,
                block_items=[item for item in block_result.get("items", []) if isinstance(item, dict)],
            )
            if rendered_result.get("ok"):
                body_markdown = str(rendered_result.get("markdown") or "")
                rendered_blocks = parse_markdown_semantic_blocks(body_markdown)
                raw_nonempty_lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
                raw_has_additional_body = len(raw_nonempty_lines) > 1
                if len(rendered_blocks) <= 1 and raw_has_additional_body:
                    degradation_note = (
                        "High-fidelity diff export fell back to raw_content because the block tree did not expose enough body content."
                    )
                else:
                    return {
                        "ok": True,
                        "title": str(rendered_result.get("title") or title or document_id),
                        "fidelity": "high",
                        "source": "blocks",
                        "body_markdown": body_markdown,
                        "body_hash": sha256_text(body_markdown),
                        "block_count": block_result.get("count"),
                        "page_count": block_result.get("page_count"),
                        "unsupported_block_count": rendered_result.get("unsupported_block_count"),
                        "unsupported_blocks": rendered_result.get("unsupported_blocks"),
                    }
            else:
                degradation_note = (
                    "High-fidelity diff export fell back to raw_content because block rendering failed."
                )
        else:
            degradation_note = (
                "High-fidelity diff export fell back to raw_content because document blocks could not be listed."
            )

    markdown_output = compose_low_fidelity_markdown(
        title=title,
        document_id=document_id,
        raw_content=raw_content,
        sync_direction="pull",
    )
    _, body_markdown, _ = split_front_matter(markdown_output)
    result = {
        "ok": True,
        "title": title,
        "fidelity": "high" if fidelity == "high" else "low",
        "source": "raw_content",
        "body_markdown": body_markdown,
        "body_hash": sha256_text(body_markdown),
        "raw_content_hash": raw_result.get("content_hash"),
        "raw_content_length": raw_result.get("content_length"),
    }
    if degradation_note:
        result["degraded_from"] = "high"
        result["degradation_note"] = degradation_note
    return result


def render_unified_diff_preview(
    local_text: str,
    remote_text: str,
    *,
    fromfile: str,
    tofile: str,
    max_lines: int = 80,
) -> Dict[str, Any]:
    preview_limit = max(1, int(max_lines))
    diff_lines = list(
        difflib.unified_diff(
            local_text.splitlines(),
            remote_text.splitlines(),
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        )
    )
    preview_lines = diff_lines[:preview_limit]
    return {
        "has_changes": bool(diff_lines),
        "line_count": len(diff_lines),
        "max_lines": preview_limit,
        "truncated": len(diff_lines) > len(preview_lines),
        "preview": "\n".join(preview_lines),
    }


def normalize_semantic_block_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def build_semantic_block(
    block_type: str,
    text: str,
    *,
    level: Optional[int] = None,
    variant: Optional[str] = None,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_text = normalize_semantic_block_text(text)
    return {
        "type": block_type,
        "level": level,
        "variant": variant,
        "language": language,
        "text": str(text or "").strip(),
        "normalized_text": normalized_text,
    }


def is_markdown_structural_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if re.match(r"^#{1,6}\s+", stripped):
        return True
    if stripped.startswith(">"):
        return True
    if stripped.startswith("```"):
        return True
    if re.match(r"^([-*+])\s+\[[ xX]\]\s+", stripped):
        return True
    if re.match(r"^([-*+])\s+", stripped):
        return True
    if re.match(r"^\d+[.)]\s+", stripped):
        return True
    if re.match(r"^!\[[^\]]*\]\([^)]+\)\s*$", stripped):
        return True
    if re.match(r"^\[[^\]]+\]\([^)]+\)\s*$", stripped):
        return True
    if re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", stripped):
        return True
    return False


def parse_markdown_semantic_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    lines = str(markdown_text or "").splitlines()
    blocks: List[Dict[str, Any]] = []
    paragraph_lines: List[str] = []
    index = 0

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        text = "\n".join(line.strip() for line in paragraph_lines if line.strip()).strip()
        if text:
            blocks.append(build_semantic_block("paragraph", text))
        paragraph_lines = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip() or None
            code_lines: List[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines) and lines[index].strip().startswith("```"):
                index += 1
            blocks.append(build_semantic_block("code", "\n".join(code_lines).rstrip(), language=language))
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
        if heading_match:
            flush_paragraph()
            blocks.append(
                build_semantic_block(
                    "heading",
                    heading_match.group(2),
                    level=len(heading_match.group(1)),
                )
            )
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines: List[str] = []
            while index < len(lines):
                current = lines[index].strip()
                if not current.startswith(">"):
                    break
                quote_lines.append(re.sub(r"^>\s?", "", current))
                index += 1
            blocks.append(build_semantic_block("quote", "\n".join(quote_lines).strip()))
            continue

        task_match = re.match(r"^[-*+]\s+\[([ xX])\]\s+(.+?)\s*$", stripped)
        if task_match:
            flush_paragraph()
            blocks.append(
                build_semantic_block(
                    "list_item",
                    task_match.group(2),
                    variant="task_done" if task_match.group(1).lower() == "x" else "task_todo",
                )
            )
            index += 1
            continue

        bullet_match = re.match(r"^[-*+]\s+(.+?)\s*$", stripped)
        if bullet_match:
            flush_paragraph()
            item_lines = [bullet_match.group(1)]
            next_index = index + 1
            while next_index < len(lines):
                continuation = lines[next_index]
                continuation_stripped = continuation.strip()
                if not continuation_stripped:
                    break
                if is_markdown_structural_line(continuation):
                    break
                if continuation.startswith((" ", "\t")):
                    item_lines.append(continuation_stripped)
                    next_index += 1
                    continue
                break
            blocks.append(build_semantic_block("list_item", "\n".join(item_lines), variant="bullet"))
            index = next_index
            continue

        ordered_match = re.match(r"^(\d+)[.)]\s+(.+?)\s*$", stripped)
        if ordered_match:
            flush_paragraph()
            item_lines = [ordered_match.group(2)]
            next_index = index + 1
            while next_index < len(lines):
                continuation = lines[next_index]
                continuation_stripped = continuation.strip()
                if not continuation_stripped:
                    break
                if is_markdown_structural_line(continuation):
                    break
                if continuation.startswith((" ", "\t")):
                    item_lines.append(continuation_stripped)
                    next_index += 1
                    continue
                break
            blocks.append(build_semantic_block("list_item", "\n".join(item_lines), variant="ordered"))
            index = next_index
            continue

        image_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", stripped)
        if image_match:
            flush_paragraph()
            alt = image_match.group(1).strip()
            target = image_match.group(2).strip()
            label = alt or target
            blocks.append(build_semantic_block("image", label, variant=target))
            index += 1
            continue

        link_match = re.match(r"^\[([^\]]+)\]\(([^)]+)\)\s*$", stripped)
        if link_match:
            flush_paragraph()
            name = link_match.group(1).strip()
            target = link_match.group(2).strip()
            blocks.append(build_semantic_block("link", name or target, variant=target))
            index += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", stripped):
            flush_paragraph()
            blocks.append(build_semantic_block("divider", stripped))
            index += 1
            continue

        paragraph_lines.append(line)
        index += 1

    flush_paragraph()
    return blocks


def summarize_semantic_block(block: Dict[str, Any]) -> Dict[str, Any]:
    block_type = str(block.get("type") or "paragraph")
    level = block.get("level")
    variant = str(block.get("variant") or "")
    language = str(block.get("language") or "")
    normalized_text = str(block.get("normalized_text") or "")
    label = block_type
    if block_type == "heading" and isinstance(level, int):
        label = f"heading-{level}"
    elif block_type == "list_item":
        label = variant or "list_item"
    elif block_type == "code":
        label = f"code:{language}" if language else "code"
    elif block_type == "image" and variant:
        label = f"image:{variant}"
    elif block_type == "link" and variant:
        label = f"link:{variant}"
    preview = normalized_text[:120]
    if len(normalized_text) > 120:
        preview += "..."
    return {
        "type": block_type,
        "label": label,
        "preview": preview,
        "text": str(block.get("text") or ""),
    }


def semantic_block_signature(block: Dict[str, Any]) -> str:
    summary = summarize_semantic_block(block)
    signature_payload = {
        "type": summary.get("type"),
        "label": summary.get("label"),
        "text": normalize_semantic_block_text(summary.get("text")),
    }
    return json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)


def summarize_semantic_block_slice(blocks: List[Dict[str, Any]], limit: int = 2) -> str:
    if not blocks:
        return "(none)"
    parts: List[str] = []
    for block in blocks[:limit]:
        summary = summarize_semantic_block(block)
        preview = summary.get("preview") or ""
        parts.append(f"{summary['label']}: {preview}" if preview else str(summary["label"]))
    if len(blocks) > limit:
        parts.append(f"+{len(blocks) - limit} more")
    return " | ".join(parts)


def render_semantic_diff_preview(local_text: str, remote_text: str, *, max_lines: int = 80) -> Dict[str, Any]:
    preview_limit = max(1, int(max_lines))
    local_blocks = parse_markdown_semantic_blocks(local_text)
    remote_blocks = parse_markdown_semantic_blocks(remote_text)
    local_signatures = [semantic_block_signature(block) for block in local_blocks]
    remote_signatures = [semantic_block_signature(block) for block in remote_blocks]
    matcher = difflib.SequenceMatcher(a=local_signatures, b=remote_signatures, autojunk=False)

    summary = {
        "equal_block_count": 0,
        "replace_block_count": 0,
        "delete_block_count": 0,
        "insert_block_count": 0,
    }
    operations: List[Dict[str, Any]] = []
    preview_lines: List[str] = []
    preview_truncated = False

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        local_slice = local_blocks[i1:i2]
        remote_slice = remote_blocks[j1:j2]
        if tag == "equal":
            summary["equal_block_count"] += len(local_slice)
            continue

        if tag == "replace":
            summary["replace_block_count"] += max(len(local_slice), len(remote_slice))
        elif tag == "delete":
            summary["delete_block_count"] += len(local_slice)
        elif tag == "insert":
            summary["insert_block_count"] += len(remote_slice)

        operation = {
            "op": tag,
            "local_count": len(local_slice),
            "remote_count": len(remote_slice),
            "local_blocks": [summarize_semantic_block(block) for block in local_slice],
            "remote_blocks": [summarize_semantic_block(block) for block in remote_slice],
        }
        operations.append(operation)

        marker = {
            "replace": "~",
            "delete": "-",
            "insert": "+",
        }.get(tag, "?")
        header = (
            f"{marker} {tag} {len(local_slice)} local block(s) -> {len(remote_slice)} remote block(s)"
            if tag == "replace"
            else f"{marker} {tag} {len(local_slice or remote_slice)} block(s)"
        )
        candidate_lines = [header]
        if local_slice:
            candidate_lines.append("  local: " + summarize_semantic_block_slice(local_slice))
        if remote_slice:
            candidate_lines.append("  remote: " + summarize_semantic_block_slice(remote_slice))
        if len(preview_lines) + len(candidate_lines) <= preview_limit:
            preview_lines.extend(candidate_lines)
        else:
            preview_truncated = True

    if not operations:
        preview_lines = ["No semantic block changes detected."]

    return {
        "format": "semantic_blocks",
        "has_changes": bool(operations),
        "block_count": {
            "local": len(local_blocks),
            "remote": len(remote_blocks),
        },
        "summary": summary,
        "operation_count": len(operations),
        "operations": operations,
        "max_lines": preview_limit,
        "truncated": preview_truncated,
        "preview": "\n".join(preview_lines[:preview_limit]),
    }


def render_semantic_blocks_to_markdown(blocks: List[Dict[str, Any]]) -> str:
    rendered: List[str] = []
    for block in blocks:
        block_type = str(block.get("type") or "paragraph")
        text = str(block.get("text") or "").rstrip()
        if block_type == "heading":
            level = int(block.get("level") or 1)
            rendered.append("#" * max(1, min(6, level)) + " " + text.strip())
            continue
        if block_type == "quote":
            quote_text = text.strip()
            rendered.append("\n".join("> " + line if line else ">" for line in quote_text.splitlines()))
            continue
        if block_type == "list_item":
            variant = str(block.get("variant") or "bullet")
            prefix = "- "
            if variant == "ordered":
                prefix = "1. "
            elif variant == "task_todo":
                prefix = "- [ ] "
            elif variant == "task_done":
                prefix = "- [x] "
            lines = text.splitlines() or [""]
            first = prefix + lines[0].strip()
            rest = [("  " + line.strip()) if line.strip() else "" for line in lines[1:]]
            rendered.append("\n".join([first, *rest]).rstrip())
            continue
        if block_type == "code":
            language = str(block.get("language") or "")
            rendered.append(f"```{language}\n{text}\n```".rstrip())
            continue
        if block_type == "image":
            target = str(block.get("variant") or "").strip()
            rendered.append(f"![{text}]({target})" if target else f"![{text}]()")
            continue
        if block_type == "link":
            target = str(block.get("variant") or "").strip()
            rendered.append(f"[{text}]({target})" if target else f"[{text}]()")
            continue
        if block_type == "divider":
            rendered.append("---")
            continue
        rendered.append(text.strip())
    return "\n\n".join(section for section in rendered if section is not None).rstrip() + "\n"


def build_semantic_change_operations(
    base_blocks: List[Dict[str, Any]],
    side_blocks: List[Dict[str, Any]],
    *,
    source: str,
) -> List[Dict[str, Any]]:
    base_signatures = [semantic_block_signature(block) for block in base_blocks]
    side_signatures = [semantic_block_signature(block) for block in side_blocks]
    matcher = difflib.SequenceMatcher(a=base_signatures, b=side_signatures, autojunk=False)
    operations: List[Dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        operations.append(
            {
                "source": source,
                "op": tag,
                "start": i1,
                "end": i2,
                "base_blocks": [dict(block) for block in base_blocks[i1:i2]],
                "blocks": [dict(block) for block in side_blocks[j1:j2]],
            }
        )
    return operations


def semantic_change_operations_overlap(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    left_start = int(left.get("start") or 0)
    left_end = int(left.get("end") or left_start)
    right_start = int(right.get("start") or 0)
    right_end = int(right.get("end") or right_start)
    left_insert = left_start == left_end
    right_insert = right_start == right_end
    if left_insert and right_insert:
        return left_start == right_start
    if left_insert:
        return right_start <= left_start <= right_end
    if right_insert:
        return left_start <= right_start <= left_end
    return not (left_end <= right_start or right_end <= left_start)


def semantic_change_operations_equivalent(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    if int(left.get("start") or 0) != int(right.get("start") or 0) or int(left.get("end") or 0) != int(right.get("end") or 0):
        return False
    left_signatures = [semantic_block_signature(block) for block in left.get("blocks", []) if isinstance(block, dict)]
    right_signatures = [semantic_block_signature(block) for block in right.get("blocks", []) if isinstance(block, dict)]
    return left_signatures == right_signatures


def summarize_semantic_change_operation(operation: Dict[str, Any]) -> Dict[str, Any]:
    blocks = [block for block in operation.get("blocks", []) if isinstance(block, dict)]
    base_blocks = [block for block in operation.get("base_blocks", []) if isinstance(block, dict)]
    return {
        "source": operation.get("source"),
        "op": operation.get("op"),
        "start": operation.get("start"),
        "end": operation.get("end"),
        "preview": summarize_semantic_block_slice(blocks),
        "replaces": summarize_semantic_block_slice(base_blocks),
    }


def render_merge_suggestion_preview(
    local_only_ops: List[Dict[str, Any]],
    remote_only_ops: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
    *,
    max_lines: int,
) -> Dict[str, Any]:
    preview_limit = max(1, int(max_lines))
    lines: List[str] = []
    truncated = False

    def add_lines(new_lines: List[str]) -> None:
        nonlocal truncated
        if len(lines) + len(new_lines) <= preview_limit:
            lines.extend(new_lines)
        else:
            truncated = True

    for operation in local_only_ops:
        summary = summarize_semantic_change_operation(operation)
        add_lines(
            [
                f"L {summary['op']} blocks @{summary['start']}:{summary['end']}",
                f"  keep local: {summary['preview']}",
            ]
        )
    for operation in remote_only_ops:
        summary = summarize_semantic_change_operation(operation)
        add_lines(
            [
                f"R {summary['op']} blocks @{summary['start']}:{summary['end']}",
                f"  keep remote: {summary['preview']}",
            ]
        )
    for conflict in conflicts:
        add_lines(
            [
                f"X overlapping changes @{conflict['start']}:{conflict['end']}",
                f"  local: {conflict['local']}",
                f"  remote: {conflict['remote']}",
            ]
        )

    if not lines:
        lines = ["No semantic merge actions were derived."]
    return {
        "max_lines": preview_limit,
        "truncated": truncated,
        "preview": "\n".join(lines[:preview_limit]),
    }


def build_semantic_merge_suggestion(
    baseline_text: str,
    local_text: str,
    remote_text: str,
    *,
    max_lines: int = 80,
) -> Dict[str, Any]:
    baseline_blocks = parse_markdown_semantic_blocks(baseline_text)
    local_blocks = parse_markdown_semantic_blocks(local_text)
    remote_blocks = parse_markdown_semantic_blocks(remote_text)
    local_ops = build_semantic_change_operations(baseline_blocks, local_blocks, source="local")
    remote_ops = build_semantic_change_operations(baseline_blocks, remote_blocks, source="remote")

    conflict_local_indices: set[int] = set()
    conflict_remote_indices: set[int] = set()
    duplicate_remote_indices: set[int] = set()
    conflicts: List[Dict[str, Any]] = []

    for local_index, local_op in enumerate(local_ops):
        for remote_index, remote_op in enumerate(remote_ops):
            if not semantic_change_operations_overlap(local_op, remote_op):
                continue
            if semantic_change_operations_equivalent(local_op, remote_op):
                duplicate_remote_indices.add(remote_index)
                continue
            conflict_local_indices.add(local_index)
            conflict_remote_indices.add(remote_index)
            conflicts.append(
                {
                    "start": min(int(local_op.get("start") or 0), int(remote_op.get("start") or 0)),
                    "end": max(int(local_op.get("end") or 0), int(remote_op.get("end") or 0)),
                    "local": summarize_semantic_block_slice([block for block in local_op.get("blocks", []) if isinstance(block, dict)]),
                    "remote": summarize_semantic_block_slice([block for block in remote_op.get("blocks", []) if isinstance(block, dict)]),
                }
            )

    local_only_ops = [operation for index, operation in enumerate(local_ops) if index not in conflict_local_indices]
    remote_only_ops = [
        operation
        for index, operation in enumerate(remote_ops)
        if index not in conflict_remote_indices and index not in duplicate_remote_indices
    ]

    merge_preview = render_merge_suggestion_preview(
        local_only_ops,
        remote_only_ops,
        conflicts,
        max_lines=max_lines,
    )

    merged_body_snapshot = None
    merged_body_hash = None
    merged_semantic_preview = None
    auto_merge_ready = not conflicts
    if auto_merge_ready:
        merged_blocks = [dict(block) for block in baseline_blocks]
        combined_ops = local_only_ops + remote_only_ops
        combined_ops.sort(key=lambda operation: (int(operation.get("start") or 0), int(operation.get("end") or 0)), reverse=True)
        for operation in combined_ops:
            start = int(operation.get("start") or 0)
            end = int(operation.get("end") or start)
            replacement = [dict(block) for block in operation.get("blocks", []) if isinstance(block, dict)]
            merged_blocks[start:end] = replacement
        merged_body = render_semantic_blocks_to_markdown(merged_blocks)
        merged_body_hash = sha256_text(merged_body)
        merged_body_snapshot = encode_text_snapshot(merged_body)
        merged_semantic_preview = render_semantic_diff_preview(baseline_text, merged_body, max_lines=max_lines)

    return {
        "ok": True,
        "kind": "semantic_three_way_merge_suggestion",
        "baseline_available": True,
        "auto_merge_ready": auto_merge_ready,
        "summary": {
            "baseline_block_count": len(baseline_blocks),
            "local_block_count": len(local_blocks),
            "remote_block_count": len(remote_blocks),
            "local_only_change_count": len(local_only_ops),
            "remote_only_change_count": len(remote_only_ops),
            "duplicate_change_count": len(duplicate_remote_indices),
            "conflict_count": len(conflicts),
        },
        "local_only_changes": [summarize_semantic_change_operation(operation) for operation in local_only_ops],
        "remote_only_changes": [summarize_semantic_change_operation(operation) for operation in remote_only_ops],
        "conflicts": conflicts,
        "preview": merge_preview.get("preview"),
        "preview_truncated": merge_preview.get("truncated"),
        "max_lines": merge_preview.get("max_lines"),
        "merged_body_hash": merged_body_hash,
        "merged_body_snapshot": merged_body_snapshot,
        "merged_preview": merged_semantic_preview,
    }


def build_conflict_merge_suggestion(
    plan: Dict[str, Any],
    index_entry: Dict[str, Any],
    doc_token: str,
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    metadata_result: Dict[str, Any],
    raw_result: Dict[str, Any],
    fidelity: str,
    max_lines: int,
) -> Dict[str, Any]:
    baseline_text = extract_index_baseline_body(index_entry)
    if not isinstance(baseline_text, str):
        return {
            "ok": False,
            "baseline_available": False,
            "error": "The index entry does not yet contain a reusable baseline body snapshot, so semantic merge suggestions are unavailable for this file.",
        }

    local_body_result = load_local_diff_body(plan)
    if not local_body_result.get("ok"):
        return {
            "ok": False,
            "baseline_available": True,
            "error": local_body_result.get("error"),
        }

    remote_body_result = build_remote_diff_body(
        document_id=doc_token,
        tenant_access_token=tenant_access_token,
        base_url=base_url,
        timeout=timeout,
        metadata_result=metadata_result,
        raw_result=raw_result,
        fidelity=fidelity,
        title_override=plan.get("title"),
    )
    if not remote_body_result.get("ok"):
        return {
            "ok": False,
            "baseline_available": True,
            "error": "sync-dir could not build a comparable remote Markdown body for semantic merge suggestions.",
        }

    suggestion = build_semantic_merge_suggestion(
        baseline_text,
        str(local_body_result.get("body_markdown") or ""),
        str(remote_body_result.get("body_markdown") or ""),
        max_lines=max_lines,
    )
    suggestion["baseline_body_hash"] = sha256_text(baseline_text)
    suggestion["local_body_hash"] = local_body_result.get("body_hash")
    suggestion["remote_body_hash"] = remote_body_result.get("body_hash")
    suggestion["fidelity"] = fidelity
    suggestion["remote_source"] = remote_body_result.get("source")
    return suggestion


def extract_merged_body_text(suggestion: Dict[str, Any]) -> Optional[str]:
    return decode_text_snapshot(suggestion.get("merged_body_snapshot"))


def replace_markdown_body_preserving_front_matter(path: Path, body_markdown: str) -> Dict[str, Any]:
    resolved_path = path.resolve()
    if not resolved_path.is_file():
        return {
            "ok": False,
            "path": str(resolved_path),
            "error": "The local Markdown file is missing, so sync-dir could not write merged content.",
        }

    text = resolved_path.read_text(encoding="utf-8")
    front_matter_match = re.match(r"(?s)\A(\ufeff?---\r?\n.*?\r?\n---)(?:\r?\n)*", text)
    if front_matter_match:
        rendered = front_matter_match.group(1) + "\n\n" + body_markdown.rstrip() + "\n"
    else:
        bom = "\ufeff" if text.startswith("\ufeff") else ""
        rendered = bom + body_markdown.rstrip() + "\n"
    resolved_path.write_text(rendered, encoding="utf-8")
    return {
        "ok": True,
        "path": str(resolved_path),
        "content_hash": sha256_text(rendered),
        "body_hash": sha256_text(body_markdown),
    }


def build_conflict_diff_preview(
    plan: Dict[str, Any],
    doc_token: str,
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    metadata_result: Dict[str, Any],
    raw_result: Dict[str, Any],
    fidelity: str,
    max_lines: int,
) -> Dict[str, Any]:
    local_body_result = load_local_diff_body(plan)
    if not local_body_result.get("ok"):
        return {
            "ok": False,
            "enabled": True,
            "fidelity": fidelity,
            "error": local_body_result.get("error"),
            "local": local_body_result,
        }

    remote_body_result = build_remote_diff_body(
        document_id=doc_token,
        tenant_access_token=tenant_access_token,
        base_url=base_url,
        timeout=timeout,
        metadata_result=metadata_result,
        raw_result=raw_result,
        fidelity=fidelity,
        title_override=plan.get("title"),
    )
    if not remote_body_result.get("ok"):
        return {
            "ok": False,
            "enabled": True,
            "fidelity": fidelity,
            "error": "sync-dir could not build a comparable remote Markdown body for diff review.",
            "remote": remote_body_result,
        }

    semantic_preview = render_semantic_diff_preview(
        str(local_body_result.get("body_markdown") or ""),
        str(remote_body_result.get("body_markdown") or ""),
        max_lines=max_lines,
    )
    unified_preview = render_unified_diff_preview(
        str(local_body_result.get("body_markdown") or ""),
        str(remote_body_result.get("body_markdown") or ""),
        fromfile=f"local:{plan.get('relative_path') or plan.get('path') or doc_token}",
        tofile=f"feishu:{doc_token}",
        max_lines=max_lines,
    )
    diff_preview = {
        **semantic_preview,
        "preview": semantic_preview.get("preview"),
        "line_preview": unified_preview,
    }
    diff_preview.update(
        {
            "ok": True,
            "enabled": True,
            "fidelity": fidelity,
            "remote_source": remote_body_result.get("source"),
            "local_title": local_body_result.get("title"),
            "remote_title": remote_body_result.get("title"),
            "local_body_hash": local_body_result.get("body_hash"),
            "remote_body_hash": remote_body_result.get("body_hash"),
        }
    )
    if remote_body_result.get("degraded_from"):
        diff_preview["degraded_from"] = remote_body_result.get("degraded_from")
        diff_preview["degradation_note"] = remote_body_result.get("degradation_note")
    if remote_body_result.get("unsupported_block_count"):
        diff_preview["unsupported_block_count"] = remote_body_result.get("unsupported_block_count")
    return diff_preview


def normalize_optional_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def extract_index_body_hash(entry: Dict[str, Any]) -> Optional[str]:
    for key in ("body_hash", "local_body_hash"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    legacy_hash = entry.get("content_hash")
    sync_direction = normalize_sync_direction(entry.get("sync_direction"))
    if isinstance(legacy_hash, str) and legacy_hash and sync_direction in {"push", "bidirectional"}:
        return legacy_hash
    return None


def extract_final_document_revision_id(write_result: Any) -> Optional[int]:
    if not isinstance(write_result, dict):
        return None
    append_result = write_result.get("append") if isinstance(write_result.get("append"), dict) else {}
    append_write_result = append_result.get("write_result") if isinstance(append_result.get("write_result"), dict) else {}
    delete_result = write_result.get("delete") if isinstance(write_result.get("delete"), dict) else {}
    create_result = write_result.get("create") if isinstance(write_result.get("create"), dict) else {}
    direct_write_result = write_result.get("write_result") if isinstance(write_result.get("write_result"), dict) else {}
    for candidate in (
        write_result.get("document_revision_id"),
        direct_write_result.get("document_revision_id"),
        append_result.get("document_revision_id"),
        append_write_result.get("document_revision_id"),
        delete_result.get("document_revision_id"),
        create_result.get("revision_id"),
    ):
        normalized = normalize_optional_int(candidate)
        if normalized is not None:
            return normalized
    return None


def summarize_local_sync_state(plan: Dict[str, Any], index_entry: Dict[str, Any]) -> Dict[str, Any]:
    current_body_hash = plan.get("body_hash") or plan.get("content_hash")
    baseline_body_hash = extract_index_body_hash(index_entry)
    changed_since_sync = (
        current_body_hash != baseline_body_hash
        if isinstance(current_body_hash, str) and current_body_hash and isinstance(baseline_body_hash, str) and baseline_body_hash
        else None
    )
    return {
        "current_body_hash": current_body_hash if isinstance(current_body_hash, str) and current_body_hash else None,
        "baseline_body_hash": baseline_body_hash,
        "changed_since_sync": changed_since_sync,
        "baseline_ready": bool(baseline_body_hash),
    }


def summarize_remote_sync_state(
    index_entry: Dict[str, Any],
    metadata_result: Dict[str, Any],
    raw_result: Dict[str, Any],
) -> Dict[str, Any]:
    current_revision_id = normalize_optional_int(metadata_result.get("revision_id"))
    baseline_revision_id = normalize_optional_int(index_entry.get("remote_revision_id"))
    current_content_hash = raw_result.get("content_hash") if isinstance(raw_result.get("content_hash"), str) else None
    baseline_content_hash = (
        index_entry.get("remote_content_hash")
        if isinstance(index_entry.get("remote_content_hash"), str) and index_entry.get("remote_content_hash")
        else None
    )
    signals: List[Dict[str, Any]] = []
    if current_revision_id is not None and baseline_revision_id is not None:
        signals.append(
            {
                "field": "revision_id",
                "baseline": baseline_revision_id,
                "current": current_revision_id,
                "changed": current_revision_id != baseline_revision_id,
            }
        )
    if current_content_hash and baseline_content_hash:
        signals.append(
            {
                "field": "raw_content_hash",
                "baseline": baseline_content_hash,
                "current": current_content_hash,
                "changed": current_content_hash != baseline_content_hash,
            }
        )
    changed_since_sync: Optional[bool]
    if any(signal.get("changed") for signal in signals):
        changed_since_sync = True
    elif signals:
        changed_since_sync = False
    else:
        changed_since_sync = None
    return {
        "current_revision_id": current_revision_id,
        "baseline_revision_id": baseline_revision_id,
        "current_content_hash": current_content_hash,
        "baseline_content_hash": baseline_content_hash,
        "changed_since_sync": changed_since_sync,
        "baseline_ready": bool(signals),
        "signals": signals,
    }


def classify_sync_drift(
    sync_direction: str,
    local_changed: Optional[bool],
    remote_changed: Optional[bool],
) -> Dict[str, Any]:
    normalized_direction = normalize_sync_direction(sync_direction)
    if local_changed is None or remote_changed is None:
        return {
            "status": "baseline_incomplete",
            "recommended_action": "rebuild_sync_baseline",
            "preferred_source": "manual_review",
            "requires_review": True,
            "message": "The index entry is missing a complete local or remote sync baseline, so conflict detection cannot be trusted yet.",
        }
    if not local_changed and not remote_changed:
        return {
            "status": "in_sync",
            "recommended_action": "noop",
            "preferred_source": "either",
            "requires_review": False,
            "message": "Neither the local Markdown body nor the remote Feishu document changed since the last recorded sync baseline.",
        }
    if local_changed and not remote_changed:
        if normalized_direction == "pull":
            return {
                "status": "local_changed_pull_only",
                "recommended_action": "review_before_pull",
                "preferred_source": "local",
                "requires_review": True,
                "message": "The local file changed since the last sync, but the file is marked pull-only. Pulling now could overwrite local work.",
            }
        if normalized_direction == "bidirectional":
            return {
                "status": "local_ahead",
                "recommended_action": "prefer_push",
                "preferred_source": "local",
                "requires_review": False,
                "message": "Only the local Markdown body changed since the last sync. A future bidirectional sync should prefer pushing this file.",
            }
        return {
            "status": "local_ahead",
            "recommended_action": "push_candidate",
            "preferred_source": "local",
            "requires_review": False,
            "message": "Only the local Markdown body changed since the last sync, so this file is a clean push candidate.",
        }
    if not local_changed and remote_changed:
        if normalized_direction == "push":
            return {
                "status": "remote_drift",
                "recommended_action": "review_before_push",
                "preferred_source": "remote",
                "requires_review": True,
                "message": "The remote Feishu document changed since the last sync. Review before pushing, or local changes could overwrite remote edits.",
            }
        if normalized_direction == "bidirectional":
            return {
                "status": "remote_ahead",
                "recommended_action": "prefer_pull",
                "preferred_source": "remote",
                "requires_review": False,
                "message": "Only the remote Feishu document changed since the last sync. A future bidirectional sync should prefer pulling this file.",
            }
        return {
            "status": "remote_ahead",
            "recommended_action": "pull_candidate",
            "preferred_source": "remote",
            "requires_review": False,
            "message": "Only the remote Feishu document changed since the last sync, so this file is a clean pull candidate.",
        }
    return {
        "status": "local_and_remote_changed",
        "recommended_action": "manual_conflict_review",
        "preferred_source": "manual_review",
        "requires_review": True,
        "message": "Both the local Markdown body and the remote Feishu document changed since the last sync baseline. Manual review is required.",
    }


def inspect_sync_dir_conflicts(
    local_plans: List[Dict[str, Any]],
    index_entries: Dict[str, Dict[str, Any]],
    remote_docs_by_token: Dict[str, Dict[str, Any]],
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    include_diff: bool = False,
    diff_fidelity: str = "low",
    diff_max_lines: int = 80,
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    risks: List[Dict[str, Any]] = []
    state_counts: Dict[str, int] = {}
    action_counts: Dict[str, int] = {}
    inspected_count = 0
    failed_count = 0
    diff_generated_count = 0
    diff_failed_count = 0
    merge_generated_count = 0
    merge_failed_count = 0
    merge_auto_ready_count = 0

    for plan in local_plans:
        doc_token = str(plan.get("doc_token") or "")
        relative_path = str(plan.get("relative_path") or "")
        if not doc_token:
            continue
        remote_doc = remote_docs_by_token.get(doc_token)
        if not remote_doc:
            continue

        inspected_count += 1
        metadata_result = probe_document_connectivity(
            tenant_access_token=tenant_access_token,
            document_id=doc_token,
            base_url=base_url,
            timeout=timeout,
        )
        if not metadata_result.get("ok"):
            failed_count += 1
            result = {
                "ok": False,
                "relative_path": relative_path,
                "doc_token": doc_token,
                "title": plan.get("title") or remote_doc.get("name"),
                "sync_direction": plan.get("sync_direction"),
                "status": "inspect_remote_metadata_failed",
                "recommended_action": "review_remote_access",
                "metadata": metadata_result,
            }
            results.append(result)
            risks.append(
                {
                    "kind": "inspect_remote_metadata_failed",
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "message": "Conflict detection could not fetch remote document metadata for this mapped file.",
                }
            )
            continue

        raw_result = get_document_raw_content(
            tenant_access_token=tenant_access_token,
            document_id=doc_token,
            base_url=base_url,
            timeout=timeout,
        )
        if not raw_result.get("ok"):
            failed_count += 1
            result = {
                "ok": False,
                "relative_path": relative_path,
                "doc_token": doc_token,
                "title": plan.get("title") or remote_doc.get("name"),
                "sync_direction": plan.get("sync_direction"),
                "status": "inspect_remote_content_failed",
                "recommended_action": "review_remote_access",
                "metadata": {
                    "revision_id": metadata_result.get("revision_id"),
                },
                "raw_content": raw_result,
            }
            results.append(result)
            risks.append(
                {
                    "kind": "inspect_remote_content_failed",
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "message": "Conflict detection could not fetch remote raw_content for this mapped file.",
                }
            )
            continue

        index_entry = index_entries.get(relative_path, {})
        local_state = summarize_local_sync_state(plan, index_entry)
        remote_state = summarize_remote_sync_state(index_entry, metadata_result, raw_result)
        comparison = classify_sync_drift(
            str(plan.get("sync_direction") or "push"),
            local_state.get("changed_since_sync"),
            remote_state.get("changed_since_sync"),
        )
        status = str(comparison["status"])
        action = str(comparison["recommended_action"])
        state_counts[status] = state_counts.get(status, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1
        result = {
            "ok": True,
            "relative_path": relative_path,
            "doc_token": doc_token,
            "title": plan.get("title") or remote_doc.get("name"),
            "sync_direction": plan.get("sync_direction"),
            "last_sync_at": index_entry.get("last_sync_at"),
            "remote_listing": {
                "title": remote_doc.get("name"),
                "folder_path": remote_doc.get("folder_path"),
                "url": remote_doc.get("url"),
            },
            "local": local_state,
            "remote": remote_state,
            "comparison": comparison,
        }
        if include_diff:
            diff_preview = build_conflict_diff_preview(
                plan=plan,
                doc_token=doc_token,
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                metadata_result=metadata_result,
                raw_result=raw_result,
                fidelity=diff_fidelity,
                max_lines=diff_max_lines,
            )
            result["diff"] = diff_preview
            if diff_preview.get("ok"):
                diff_generated_count += 1
            else:
                diff_failed_count += 1
                risks.append(
                    {
                        "kind": "conflict_diff_failed",
                        "relative_path": relative_path,
                        "doc_token": doc_token,
                        "message": diff_preview.get("error")
                        or "sync-dir could not build a local vs remote diff preview for this mapped file.",
                    }
                )
        if status == "local_and_remote_changed":
            merge_suggestion = build_conflict_merge_suggestion(
                plan=plan,
                index_entry=index_entry,
                doc_token=doc_token,
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                metadata_result=metadata_result,
                raw_result=raw_result,
                fidelity=diff_fidelity,
                max_lines=diff_max_lines,
            )
            result["merge_suggestion"] = merge_suggestion
            if merge_suggestion.get("ok"):
                merge_generated_count += 1
                if merge_suggestion.get("auto_merge_ready"):
                    merge_auto_ready_count += 1
            else:
                merge_failed_count += 1
                if merge_suggestion.get("error"):
                    risks.append(
                        {
                            "kind": "merge_suggestion_unavailable",
                            "relative_path": relative_path,
                            "doc_token": doc_token,
                            "message": str(merge_suggestion.get("error")),
                        }
                    )
        results.append(result)
        if comparison.get("requires_review"):
            risks.append(
                {
                    "kind": status,
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "message": comparison.get("message"),
                }
            )

    review_required_count = sum(
        1
        for result in results
        if isinstance(result, dict)
        and isinstance(result.get("comparison"), dict)
        and result["comparison"].get("requires_review")
    )
    return {
        "enabled": True,
        "inspected_count": inspected_count,
        "failed_count": failed_count,
        "review_required_count": review_required_count,
        "state_counts": state_counts,
        "recommended_action_counts": action_counts,
        "diff": {
            "enabled": bool(include_diff),
            "fidelity": diff_fidelity if include_diff else None,
            "max_lines": max(1, int(diff_max_lines)) if include_diff else None,
            "generated_count": diff_generated_count,
            "failed_count": diff_failed_count,
        },
        "merge_suggestions": {
            "enabled": True,
            "fidelity": diff_fidelity,
            "generated_count": merge_generated_count,
            "failed_count": merge_failed_count,
            "auto_merge_ready_count": merge_auto_ready_count,
        },
        "results": results,
        "risks": risks,
    }


def resolve_drive_folder_reference(
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    folder_token: Optional[str] = None,
) -> Dict[str, Any]:
    if folder_token:
        return {
            "ok": True,
            "source": "arg",
            "token": folder_token,
            "meta": None,
        }

    root_result = get_root_folder_meta(
        tenant_access_token=tenant_access_token,
        base_url=base_url,
        timeout=timeout,
    )
    if not root_result["ok"]:
        return {
            "ok": False,
            "source": "root_meta",
            "token": None,
            "meta": root_result,
        }
    return {
        "ok": True,
        "source": "root_meta",
        "token": root_result["token"],
        "meta": root_result,
    }


def list_drive_folder_contents(
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    folder_token: Optional[str] = None,
    recursive: bool = False,
    max_depth: int = 20,
    page_size: int = 100,
    max_pages: int = 20,
) -> Dict[str, Any]:
    folder_ref = resolve_drive_folder_reference(
        tenant_access_token=tenant_access_token,
        base_url=base_url,
        timeout=timeout,
        folder_token=folder_token,
    )
    if not folder_ref["ok"]:
        return {
            "kind": "drive_list_folder_tree",
            "ok": False,
            "folder": folder_ref,
            "recursive": recursive,
            "max_depth": max_depth,
            "page_count": 0,
            "item_count": 0,
            "folder_count": 0,
            "file_count": 0,
            "items": [],
            "pages": [],
            "error": "Failed to resolve the starting folder token.",
        }

    queue: List[Tuple[str, str, int]] = [(str(folder_ref["token"]), "", 0)]
    visited_folders = {str(folder_ref["token"])}
    items: List[Dict[str, Any]] = []
    pages: List[Dict[str, Any]] = []
    page_count = 0

    while queue:
        current_token, current_path, depth = queue.pop(0)
        page_token: Optional[str] = None
        while True:
            if page_count >= max_pages:
                return {
                    "kind": "drive_list_folder_tree",
                    "ok": False,
                    "folder": folder_ref,
                    "recursive": recursive,
                    "max_depth": max_depth,
                    "page_count": page_count,
                    "item_count": len(items),
                    "folder_count": sum(1 for item in items if is_drive_folder_type(item.get("type"))),
                    "file_count": sum(1 for item in items if not is_drive_folder_type(item.get("type"))),
                    "items": items,
                    "pages": pages,
                    "error": f"Exceeded max_pages={max_pages} while listing folder contents.",
                }

            page_result = list_drive_files(
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                folder_token=current_token,
                page_size=page_size,
                page_token=page_token,
            )
            page_count += 1
            pages.append(
                {
                    "page": page_count,
                    "folder_token": current_token,
                    "folder_path": current_path,
                    "depth": depth,
                    "ok": page_result["ok"],
                    "status": page_result["status"],
                    "code": page_result["code"],
                    "msg": page_result["msg"],
                    "count": page_result["count"],
                    "has_more": page_result["has_more"],
                    "next_page_token": page_result["next_page_token"],
                }
            )
            if not page_result["ok"]:
                return {
                    "kind": "drive_list_folder_tree",
                    "ok": False,
                    "folder": folder_ref,
                    "recursive": recursive,
                    "max_depth": max_depth,
                    "page_count": page_count,
                    "item_count": len(items),
                    "folder_count": sum(1 for item in items if is_drive_folder_type(item.get("type"))),
                    "file_count": sum(1 for item in items if not is_drive_folder_type(item.get("type"))),
                    "items": items,
                    "pages": pages,
                    "failed_page": page_result,
                    "error": "Failed to list a drive folder page.",
                }

            for entry in page_result["files"]:
                name = str(entry.get("name") or entry.get("token") or "untitled")
                relative_path = "/".join(part for part in (current_path, name) if part)
                enriched = dict(entry)
                enriched["folder_token"] = current_token
                enriched["folder_path"] = current_path
                enriched["relative_path"] = relative_path
                enriched["depth"] = depth + 1
                items.append(enriched)
                if (
                    recursive
                    and is_drive_folder_type(entry.get("type"))
                    and depth + 1 <= max_depth
                ):
                    child_token = str(entry.get("token") or "")
                    if child_token and child_token not in visited_folders:
                        visited_folders.add(child_token)
                        queue.append((child_token, relative_path, depth + 1))

            if not page_result["has_more"]:
                break
            page_token = page_result["next_page_token"]
            if not page_token:
                break

    return {
        "kind": "drive_list_folder_tree",
        "ok": True,
        "folder": folder_ref,
        "recursive": recursive,
        "max_depth": max_depth,
        "page_count": page_count,
        "item_count": len(items),
        "folder_count": sum(1 for item in items if is_drive_folder_type(item.get("type"))),
        "file_count": sum(1 for item in items if not is_drive_folder_type(item.get("type"))),
        "items": items,
        "pages": pages,
    }


def build_doc_token_index(index_entries: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for relative_path, entry in index_entries.items():
        doc_token = entry.get("doc_token")
        if isinstance(doc_token, str) and doc_token:
            normalized = dict(entry)
            normalized["relative_path"] = relative_path
            result[doc_token] = normalized
    return result


def build_directory_folder_token_index(
    index_entries: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    folder_tokens: Dict[str, str] = {}
    conflicts: Dict[str, set[str]] = {}
    for relative_path, entry in index_entries.items():
        folder_token = entry.get("folder_token")
        if not isinstance(folder_token, str) or not folder_token:
            continue
        relative_dir = normalize_relative_dir(Path(relative_path).parent.as_posix())
        existing = folder_tokens.get(relative_dir)
        if existing is None:
            folder_tokens[relative_dir] = folder_token
            continue
        if existing != folder_token:
            conflicts.setdefault(relative_dir, {existing}).add(folder_token)
    return (
        folder_tokens,
        {key: sorted(values) for key, values in conflicts.items()},
    )


def ensure_remote_folder_hierarchy(
    tenant_access_token: str,
    root_folder_token: str,
    relative_dir: str,
    base_url: str,
    timeout: int,
    folder_cache: Optional[Dict[str, str]] = None,
    child_listing_cache: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    normalized_relative_dir = normalize_relative_dir(relative_dir)
    if folder_cache is None:
        folder_cache = {}
    if child_listing_cache is None:
        child_listing_cache = {}

    folder_cache.setdefault("", root_folder_token)

    if not normalized_relative_dir:
        return {
            "ok": True,
            "relative_dir": "",
            "folder_token": root_folder_token,
            "created": [],
            "reused": [{"relative_dir": "", "folder_token": root_folder_token}],
        }

    current_token = root_folder_token
    current_relative_dir = ""
    created: List[Dict[str, Any]] = []
    reused: List[Dict[str, Any]] = []

    for raw_part in normalized_relative_dir.split("/"):
        folder_name = raw_part.strip()
        if not folder_name:
            continue
        current_relative_dir = "/".join(part for part in (current_relative_dir, folder_name) if part)
        cached_token = folder_cache.get(current_relative_dir)
        if cached_token:
            current_token = cached_token
            reused.append(
                {
                    "relative_dir": current_relative_dir,
                    "folder_token": current_token,
                    "source": "cache",
                }
            )
            continue

        child_folders = child_listing_cache.get(current_token)
        if child_folders is None:
            listing = list_drive_files(
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                folder_token=current_token,
                page_size=200,
            )
            if not listing["ok"]:
                return {
                    "ok": False,
                    "relative_dir": current_relative_dir,
                    "parent_folder_token": current_token,
                    "created": created,
                    "reused": reused,
                    "listing": listing,
                    "error": "Failed to enumerate existing child folders while resolving the remote folder path.",
                }
            child_folders = {
                str(item.get("name") or ""): item
                for item in listing.get("files", [])
                if is_drive_folder_type(item.get("type")) and str(item.get("name") or "").strip()
            }
            child_listing_cache[current_token] = child_folders

        existing_folder = child_folders.get(folder_name)
        if isinstance(existing_folder, dict) and existing_folder.get("token"):
            current_token = str(existing_folder["token"])
            folder_cache[current_relative_dir] = current_token
            reused.append(
                {
                    "relative_dir": current_relative_dir,
                    "folder_token": current_token,
                    "source": "remote_existing",
                }
            )
            continue

        create_result = create_drive_folder(
            tenant_access_token=tenant_access_token,
            name=folder_name,
            parent_folder_token=current_token,
            base_url=base_url,
            timeout=timeout,
        )
        if not create_result["ok"]:
            return {
                "ok": False,
                "relative_dir": current_relative_dir,
                "parent_folder_token": current_token,
                "created": created,
                "reused": reused,
                "create": create_result,
                "error": "Failed to create a remote Feishu folder for the local directory mirror.",
            }

        current_token = str(create_result["token"])
        folder_cache[current_relative_dir] = current_token
        child_folders[folder_name] = {
            "name": create_result.get("name") or folder_name,
            "type": "folder",
            "token": current_token,
            "parent_token": create_result.get("parent_folder_token"),
            "url": create_result.get("url"),
        }
        child_listing_cache[current_token] = child_listing_cache.get(current_token, {})
        created.append(
            {
                "relative_dir": current_relative_dir,
                "folder_token": current_token,
                "name": create_result.get("name") or folder_name,
                "parent_folder_token": create_result.get("parent_folder_token"),
            }
        )

    return {
        "ok": True,
        "relative_dir": normalized_relative_dir,
        "folder_token": current_token,
        "created": created,
        "reused": reused,
    }


def ensure_unique_relative_markdown_path(
    relative_path: str,
    used_paths: set[str],
    token: str,
) -> str:
    candidate = relative_path
    if candidate not in used_paths:
        return candidate
    base = candidate[:-3] if candidate.lower().endswith(".md") else candidate
    suffix = sanitize_path_component(token[-6:] if token else "copy", fallback="copy")
    index = 1
    while True:
        numbered = f"{base}-{suffix}-{index}.md"
        if numbered not in used_paths:
            return numbered
        index += 1


def derive_relative_pull_path(
    remote_item: Dict[str, Any],
    doc_token_index: Dict[str, Dict[str, Any]],
    used_paths: set[str],
) -> Tuple[str, str]:
    remote_token = str(remote_item.get("token") or "")
    existing = doc_token_index.get(remote_token)
    if existing:
        relative_path = str(existing["relative_path"])
        used_paths.add(relative_path)
        return relative_path, "feishu-index.json"

    folder_parts = [
        sanitize_path_component(part, fallback="folder")
        for part in str(remote_item.get("folder_path") or "").split("/")
        if part
    ]
    base_name = sanitize_path_component(remote_item.get("name") or remote_token, fallback=remote_token or "untitled")
    filename = ensure_markdown_extension(base_name)
    relative_path = "/".join([*folder_parts, filename]) if folder_parts else filename
    unique_relative_path = ensure_unique_relative_markdown_path(relative_path, used_paths, remote_token)
    used_paths.add(unique_relative_path)
    return unique_relative_path, "derived_from_remote_path"


def resolve_pull_output_path(
    document_title: str,
    document_id: str,
    output_path: Optional[str],
    root: Optional[Path],
    relative_path_hint: Optional[str] = None,
) -> Tuple[Path, Optional[Path], str]:
    root_path = root.resolve() if root else None
    if output_path:
        explicit_path = Path(output_path).resolve()
        if explicit_path.exists() and explicit_path.is_dir():
            filename = ensure_markdown_extension(
                sanitize_path_component(document_title or document_id, fallback=document_id or "document")
            )
            final_path = explicit_path / filename
        elif explicit_path.suffix.lower() == ".md":
            final_path = explicit_path
        elif explicit_path.exists() and explicit_path.is_file():
            final_path = explicit_path
        else:
            final_path = explicit_path
        effective_root = root_path or final_path.parent.resolve()
    else:
        effective_root = root_path or Path.cwd().resolve()
        relative_hint = relative_path_hint or ensure_markdown_extension(
            sanitize_path_component(document_title or document_id, fallback=document_id or "document")
        )
        final_path = (effective_root / relative_hint).resolve()

    if effective_root and effective_root not in final_path.parents and final_path != effective_root:
        raise ValueError(f"Output path {final_path} is not under expected root {effective_root}")

    relative_path = (
        final_path.relative_to(effective_root).as_posix()
        if effective_root is not None and (effective_root in final_path.parents or final_path == effective_root)
        else final_path.name
    )
    return final_path, effective_root, relative_path


def write_markdown_output(path: Path, content: str, overwrite: bool) -> Dict[str, Any]:
    if path.exists() and path.is_dir():
        return {
            "ok": False,
            "path": str(path),
            "error": "Output path points to a directory, not a Markdown file.",
        }
    if path.exists() and not overwrite:
        return {
            "ok": False,
            "path": str(path),
            "error": "Output Markdown file already exists. Re-run with --overwrite to replace it.",
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "bytes_written": len(content.encode("utf-8")),
        "content_hash": sha256_text(content),
    }


def backup_index_snapshot(index_path: Path, backup_run_dir: Path) -> Dict[str, Any]:
    payload = load_index_payload(index_path)
    snapshot_path = backup_run_dir / "index" / INDEX_FILENAME
    write_json_file(snapshot_path, payload)
    return {
        "ok": True,
        "path": str(snapshot_path),
        "entry_count": len(payload.get("files", [])),
        "content_hash": sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    }


def backup_remote_document_snapshot(
    candidate: Dict[str, Any],
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    backup_run_dir: Path,
    *,
    scope: str = "remote-docs",
    fidelity: str = "low",
    backup_reason: str = "sync safety backup",
) -> Dict[str, Any]:
    doc_token = str(candidate.get("doc_token") or "")
    relative_path = str(candidate.get("relative_path") or "")
    title_hint = str(candidate.get("title") or doc_token or "document")
    if not doc_token:
        return {
            "ok": False,
            "doc_token": None,
            "relative_path": relative_path,
            "error": "Missing doc_token for remote backup.",
        }

    metadata_result = probe_document_connectivity(
        tenant_access_token=tenant_access_token,
        document_id=doc_token,
        base_url=base_url,
        timeout=timeout,
    )
    if not metadata_result["ok"]:
        return {
            "ok": False,
            "doc_token": doc_token,
            "relative_path": relative_path,
            "title": title_hint,
            "metadata": metadata_result,
            "error": "Failed to fetch document metadata before remote backup.",
        }

    raw_result = get_document_raw_content(
        tenant_access_token=tenant_access_token,
        document_id=doc_token,
        base_url=base_url,
        timeout=timeout,
    )
    if not raw_result["ok"]:
        return {
            "ok": False,
            "doc_token": doc_token,
            "relative_path": relative_path,
            "title": title_hint,
            "metadata": metadata_result,
            "raw_content": raw_result,
            "error": "Failed to fetch raw_content before remote backup.",
        }

    title = str(metadata_result.get("title") or title_hint or doc_token)
    candidate_slug = sanitize_path_component(relative_path or title or doc_token, fallback=doc_token)
    token_slug = sanitize_path_component(doc_token[-6:] if len(doc_token) >= 6 else doc_token, fallback="token")
    candidate_dir = backup_run_dir / scope / f"{candidate_slug}-{token_slug}"
    candidate_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = candidate_dir / "document.md"
    raw_content_path = candidate_dir / "raw-content.txt"
    metadata_path = candidate_dir / "metadata.json"
    export_result = build_remote_diff_body(
        document_id=doc_token,
        tenant_access_token=tenant_access_token,
        base_url=base_url,
        timeout=timeout,
        metadata_result=metadata_result,
        raw_result=raw_result,
        fidelity=fidelity,
        title_override=title,
    )
    if not export_result.get("ok"):
        return {
            "ok": False,
            "doc_token": doc_token,
            "relative_path": relative_path,
            "title": title,
            "metadata": metadata_result,
            "raw_content": raw_result,
            "export": export_result,
            "error": "Failed to build the remote Markdown backup payload.",
        }

    export_title = str(export_result.get("title") or title or doc_token)
    export_fidelity = "blocks" if export_result.get("source") == "blocks" else "raw_content"
    markdown_output = compose_exported_markdown(
        title=export_title,
        document_id=doc_token,
        body_markdown=str(export_result.get("body_markdown") or ""),
        sync_direction="pull",
        fidelity=export_fidelity,
    )
    markdown_path.write_text(markdown_output, encoding="utf-8")
    raw_content_path.write_text(str(raw_result.get("content") or ""), encoding="utf-8")
    snapshot_payload = {
        "backed_up_at": current_timestamp_utc(),
        "reason": backup_reason,
        "candidate": candidate,
        "metadata": {
            "document_id": metadata_result.get("document_id"),
            "resolved_document_id": metadata_result.get("resolved_document_id"),
            "title": metadata_result.get("title"),
            "revision_id": metadata_result.get("revision_id"),
        },
        "raw_content": {
            "content_length": raw_result.get("content_length"),
            "content_hash": raw_result.get("content_hash"),
        },
        "export": {
            "requested_fidelity": fidelity,
            "source": export_result.get("source"),
            "body_hash": export_result.get("body_hash"),
            "degraded_from": export_result.get("degraded_from"),
            "degradation_note": export_result.get("degradation_note"),
            "unsupported_block_count": export_result.get("unsupported_block_count"),
        },
    }
    write_json_file(metadata_path, snapshot_payload)

    return {
        "ok": True,
        "doc_token": doc_token,
        "relative_path": relative_path,
        "title": title,
        "backup_dir": str(candidate_dir),
        "markdown_path": str(markdown_path),
        "raw_content_path": str(raw_content_path),
        "metadata_path": str(metadata_path),
        "fidelity": fidelity,
        "export_source": export_result.get("source"),
        "body_hash": export_result.get("body_hash"),
        "raw_content_hash": raw_result.get("content_hash"),
        "raw_content_length": raw_result.get("content_length"),
        "degraded_from": export_result.get("degraded_from"),
        "degradation_note": export_result.get("degradation_note"),
    }


def backup_remote_document_for_prune(
    candidate: Dict[str, Any],
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    backup_run_dir: Path,
) -> Dict[str, Any]:
    return backup_remote_document_snapshot(
        candidate=candidate,
        tenant_access_token=tenant_access_token,
        base_url=base_url,
        timeout=timeout,
        backup_run_dir=backup_run_dir,
        scope="remote-docs",
        fidelity="low",
        backup_reason="sync-dir prune backup",
    )


def backup_local_markdown_snapshot(
    file_path: Path,
    relative_path: str,
    backup_run_dir: Path,
    *,
    reason: str = "sync safety backup",
) -> Dict[str, Any]:
    resolved_path = file_path.resolve()
    if not resolved_path.is_file():
        return {
            "ok": False,
            "path": str(resolved_path),
            "relative_path": relative_path,
            "error": "The local Markdown file is missing, so sync-dir could not create a local backup snapshot.",
        }

    backup_path = (backup_run_dir / "local-files" / relative_path).resolve()
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(resolved_path, backup_path)
    metadata_path = backup_path.with_suffix(backup_path.suffix + ".metadata.json")
    write_json_file(
        metadata_path,
        {
            "backed_up_at": current_timestamp_utc(),
            "reason": reason,
            "path": str(resolved_path),
            "relative_path": relative_path,
            "content_hash": sha256_text(resolved_path.read_text(encoding="utf-8")),
        },
    )
    return {
        "ok": True,
        "path": str(resolved_path),
        "relative_path": relative_path,
        "backup_path": str(backup_path),
        "metadata_path": str(metadata_path),
    }


def execute_pull_markdown(
    document_id: str,
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    output_path: Optional[str] = None,
    root: Optional[Path] = None,
    index_path: Optional[str] = None,
    overwrite: bool = False,
    sync_direction: str = "pull",
    title_override: Optional[str] = None,
    folder_token: Optional[str] = None,
    relative_path_hint: Optional[str] = None,
    write_index: bool = False,
    fidelity: str = "low",
) -> Dict[str, Any]:
    metadata_result = probe_document_connectivity(
        tenant_access_token=tenant_access_token,
        document_id=document_id,
        base_url=base_url,
        timeout=timeout,
    )
    if not metadata_result["ok"]:
        return {
            "ok": False,
            "document_id": document_id,
            "action": "get_document",
            "metadata": metadata_result,
        }

    raw_result = get_document_raw_content(
        tenant_access_token=tenant_access_token,
        document_id=document_id,
        base_url=base_url,
        timeout=timeout,
    )
    if not raw_result["ok"]:
        return {
            "ok": False,
            "document_id": document_id,
            "action": "get_raw_content",
            "metadata": metadata_result,
            "raw_content": raw_result,
        }

    title = str(title_override or metadata_result.get("title") or document_id)
    resolved_title = title
    export_notes: List[str] = []
    body_markdown_output = ""
    markdown_output: Optional[str] = None
    fidelity_result: Dict[str, Any]

    if fidelity == "high":
        block_result = fetch_all_document_blocks(
            tenant_access_token=tenant_access_token,
            document_id=document_id,
            base_url=base_url,
            timeout=timeout,
        )
        if not block_result["ok"]:
            return {
                "ok": False,
                "document_id": document_id,
                "title": title,
                "fidelity": "high",
                "action": "list_document_blocks",
                "metadata": metadata_result,
                "raw_content": raw_result,
                "blocks": block_result,
            }
        rendered_result = render_high_fidelity_markdown(
            document_id=document_id,
            document_title=title,
            block_items=[
                item for item in block_result.get("items", [])
                if isinstance(item, dict)
            ],
        )
        if not rendered_result["ok"]:
            return {
                "ok": False,
                "document_id": document_id,
                "title": title,
                "fidelity": "high",
                "action": "render_document_blocks",
                "metadata": metadata_result,
                "raw_content": raw_result,
                "blocks": block_result,
                "render": rendered_result,
            }
        resolved_title = str(rendered_result.get("title") or title or document_id)
        body_markdown_output = str(rendered_result.get("markdown") or "")
        markdown_output = compose_exported_markdown(
            title=resolved_title,
            document_id=document_id,
            body_markdown=body_markdown_output,
            sync_direction=sync_direction,
            fidelity="blocks",
        )
        export_notes.append(
            "pull-markdown used the Feishu block tree to rebuild a higher-fidelity Markdown export for common block types."
        )
        if rendered_result.get("unsupported_block_count"):
            export_notes.append(
                f"The block export still emitted placeholders for {rendered_result['unsupported_block_count']} unsupported block(s)."
            )
        fidelity_result = {
            "mode": "high",
            "source": "blocks",
            "block_count": block_result.get("count"),
            "page_count": block_result.get("page_count"),
            "unsupported_block_count": rendered_result.get("unsupported_block_count"),
            "unsupported_blocks": rendered_result.get("unsupported_blocks"),
        }
    else:
        markdown_output = compose_low_fidelity_markdown(
            title=title,
            document_id=document_id,
            raw_content=str(raw_result.get("content") or ""),
            sync_direction=sync_direction,
        )
        _, body_markdown_output, _ = split_front_matter(markdown_output)
        export_notes.append(
            "pull-markdown currently uses the Feishu raw_content API, so Markdown fidelity is intentionally low."
        )
        fidelity_result = {
            "mode": "low",
            "source": "raw_content",
            "content_length": raw_result.get("content_length"),
            "content_hash": raw_result.get("content_hash"),
        }

    final_output_path, effective_root, relative_path = resolve_pull_output_path(
        document_title=resolved_title,
        document_id=document_id,
        output_path=output_path,
        root=root,
        relative_path_hint=relative_path_hint,
    )
    write_result = write_markdown_output(final_output_path, markdown_output, overwrite=overwrite)
    if not write_result["ok"]:
        return {
            "ok": False,
            "document_id": document_id,
            "title": resolved_title,
            "relative_path": relative_path,
            "fidelity": fidelity,
            "metadata": metadata_result,
            "raw_content": raw_result,
            "write_local": write_result,
        }

    index_entry = None
    resolved_index_path = None
    if write_index and effective_root is not None:
        resolved_index_path = resolve_index_path(effective_root, index_path)
        body_hash = sha256_text(body_markdown_output)
        index_entry = update_index_entry(
            resolved_index_path,
            relative_path,
            {
                "doc_token": document_id,
                "title": resolved_title,
                "content_hash": write_result.get("content_hash"),
                "body_hash": body_hash,
                "baseline_body_snapshot": encode_text_snapshot(body_markdown_output),
                "last_sync_at": current_timestamp_utc(),
                "sync_direction": sync_direction,
                "folder_token": folder_token,
                "remote_revision_id": metadata_result.get("revision_id"),
                "remote_content_hash": raw_result.get("content_hash"),
                "last_pull_fidelity": fidelity_result.get("source"),
                "last_sync_operation": "pull",
            },
        )

    return {
        "ok": True,
        "document_id": document_id,
        "title": resolved_title,
        "relative_path": relative_path,
        "output_path": str(final_output_path),
        "root": str(effective_root) if effective_root else None,
        "fidelity": "high" if fidelity == "high" else "low",
        "sync_direction": sync_direction,
        "body_hash": sha256_text(body_markdown_output),
        "metadata": metadata_result,
        "raw_content": {
            "content_length": raw_result.get("content_length"),
            "content_hash": raw_result.get("content_hash"),
        },
        "export": fidelity_result,
        "write_local": write_result,
        "index_path": str(resolved_index_path) if resolved_index_path else None,
        "index_entry": index_entry,
        "notes": export_notes
        + [
            "The pulled file includes front matter with feishu_doc_token and feishu_sync_direction for later mapping reuse.",
        ],
    }


def build_sync_dir_dry_run(
    root: Path,
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    folder_token: Optional[str] = None,
    index_path: Optional[str] = None,
    recursive: bool = True,
    max_depth: int = 20,
    page_size: int = 100,
    max_pages: int = 20,
    prune: bool = False,
    detect_conflicts: bool = False,
    include_diff: bool = False,
    diff_fidelity: str = "low",
    diff_max_lines: int = 80,
) -> Dict[str, Any]:
    resolved_root = root.resolve()
    if not resolved_root.is_dir():
        raise FileNotFoundError(f"Sync root not found: {resolved_root}")

    effective_index_path = resolve_index_path(resolved_root, index_path)
    index_entries = load_index(effective_index_path)
    doc_token_index = build_doc_token_index(index_entries)
    local_paths = iter_markdown_files(resolved_root)
    local_plans = [
        plan_file(path, mode="push", root=resolved_root, index_path=effective_index_path)
        for path in local_paths
    ]

    remote_listing = list_drive_folder_contents(
        tenant_access_token=tenant_access_token,
        base_url=base_url,
        timeout=timeout,
        folder_token=folder_token,
        recursive=recursive,
        max_depth=max_depth,
        page_size=page_size,
        max_pages=max_pages,
    )
    if not remote_listing["ok"]:
        return {
            "ok": False,
            "root": str(resolved_root),
            "index_path": str(effective_index_path),
            "local_plans": local_plans,
            "remote_listing": remote_listing,
            "error": "Failed to build remote listing for sync-dir dry run.",
        }

    remote_docs = [item for item in remote_listing["items"] if is_drive_docx_type(item.get("type"))]
    remote_docs_by_token = {
        str(item.get("token")): item
        for item in remote_docs
        if isinstance(item.get("token"), str) and item.get("token")
    }
    mapped_doc_tokens = set(doc_token_index.keys())
    local_doc_tokens = {
        str(plan["doc_token"])
        for plan in local_plans
        if isinstance(plan.get("doc_token"), str) and plan.get("doc_token")
    }
    local_relative_paths = {str(plan["relative_path"]) for plan in local_plans}
    risks: List[Dict[str, Any]] = []

    for plan in local_plans:
        doc_token = plan.get("doc_token")
        if isinstance(doc_token, str) and doc_token and doc_token not in remote_docs_by_token:
            risks.append(
                {
                    "kind": "visibility_missing",
                    "relative_path": plan["relative_path"],
                    "doc_token": doc_token,
                    "message": "The file is mapped to a remote doc token that is not visible in the current tenant folder listing.",
                }
            )
        if plan.get("sync_direction") == "pull":
            risks.append(
                {
                    "kind": "pull_only_local_file",
                    "relative_path": plan["relative_path"],
                    "message": "This local file is marked pull-only and will be skipped by tenant push flows unless explicitly overridden.",
                }
            )

    used_paths = set(local_relative_paths)
    remote_pull_candidates: List[Dict[str, Any]] = []
    for remote_doc in remote_docs:
        token = str(remote_doc.get("token") or "")
        if not token or token in local_doc_tokens or token in mapped_doc_tokens:
            continue
        relative_path, path_source = derive_relative_pull_path(remote_doc, doc_token_index, used_paths)
        remote_pull_candidates.append(
            {
                "doc_token": token,
                "title": remote_doc.get("name"),
                "relative_path": relative_path,
                "path_source": path_source,
                "folder_path": remote_doc.get("folder_path"),
                "url": remote_doc.get("url"),
                "action": "pull_remote_doc",
            }
        )

    prune_candidates: List[Dict[str, Any]] = []
    if prune:
        for relative_path, entry in index_entries.items():
            doc_token = entry.get("doc_token")
            if not isinstance(doc_token, str) or not doc_token:
                continue
            if relative_path in local_relative_paths:
                continue
            remote_doc = remote_docs_by_token.get(doc_token)
            if not remote_doc:
                continue
            prune_candidates.append(
                {
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "title": entry.get("title") or remote_doc.get("name"),
                    "action": "prune_remote_doc_candidate",
                    "reason": "Index entry exists, but the local Markdown file is missing under the sync root.",
                }
            )

    action_counts: Dict[str, int] = {}
    for plan in local_plans:
        action = str(plan.get("action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1

    conflict_detection: Optional[Dict[str, Any]] = None
    if detect_conflicts:
        conflict_detection = inspect_sync_dir_conflicts(
            local_plans=local_plans,
            index_entries=index_entries,
            remote_docs_by_token=remote_docs_by_token,
            tenant_access_token=tenant_access_token,
            base_url=base_url,
            timeout=timeout,
            include_diff=include_diff,
            diff_fidelity=diff_fidelity,
            diff_max_lines=diff_max_lines,
        )
        risks.extend(conflict_detection.get("risks", []))

    summary = {
        "local_file_count": len(local_plans),
        "remote_doc_count": len(remote_docs),
        "remote_pull_candidate_count": len(remote_pull_candidates),
        "prune_candidate_count": len(prune_candidates),
        "risk_count": len(risks),
        "local_action_counts": action_counts,
    }
    if conflict_detection is not None:
        summary.update(
            {
                "conflict_detection_enabled": True,
                "inspected_mapped_doc_count": conflict_detection.get("inspected_count", 0),
                "conflict_review_count": conflict_detection.get("review_required_count", 0),
                "conflict_inspection_failed_count": conflict_detection.get("failed_count", 0),
                "conflict_diff_preview_count": conflict_detection.get("diff", {}).get("generated_count", 0),
                "conflict_diff_failed_count": conflict_detection.get("diff", {}).get("failed_count", 0),
                "merge_suggestion_count": conflict_detection.get("merge_suggestions", {}).get("generated_count", 0),
                "merge_suggestion_failed_count": conflict_detection.get("merge_suggestions", {}).get("failed_count", 0),
                "merge_auto_ready_count": conflict_detection.get("merge_suggestions", {}).get("auto_merge_ready_count", 0),
            }
        )

    return {
        "ok": True,
        "root": str(resolved_root),
        "index_path": str(effective_index_path),
        "dry_run": True,
        "recursive": recursive,
        "prune": prune,
        "summary": summary,
        "local_plans": local_plans,
        "remote_listing": {
            "folder": remote_listing["folder"],
            "recursive": remote_listing["recursive"],
            "page_count": remote_listing["page_count"],
            "item_count": remote_listing["item_count"],
            "folder_count": remote_listing["folder_count"],
            "file_count": remote_listing["file_count"],
        },
        "remote_pull_candidates": remote_pull_candidates,
        "prune_candidates": prune_candidates,
        "conflict_detection": conflict_detection,
        "risks": risks,
        "notes": [
            "sync-dir dry-run builds the plan without modifying remote docs or feishu-index.json.",
            "Prune execution is available only with --prune --confirm-prune and still does not perform mixed push or pull execution.",
            "Remote pull candidates are derived from visible app-scoped docx files that are not yet mapped locally.",
            "Prune candidates are limited to index-mapped remote docs whose local Markdown files are now missing.",
        ]
        + (
            [
                "With --detect-conflicts, sync-dir also fetches remote metadata and raw_content for mapped visible docs so the plan can classify local drift, remote drift, and review-required conflicts."
            ]
            if detect_conflicts
            else []
        )
        + (
            [
                f"With --include-diff, each inspected file also includes a semantic block diff preview plus a truncated {diff_fidelity}-fidelity line diff capped at {max(1, int(diff_max_lines))} lines."
            ]
            if detect_conflicts and include_diff
            else []
        ),
    }


def build_bidirectional_sync_execution_plan(
    plan: Dict[str, Any],
    *,
    allow_auto_merge: bool = False,
    adopt_remote_new: bool = False,
    include_create_flow: bool = False,
) -> Dict[str, Any]:
    conflict_detection = plan.get("conflict_detection")
    local_plans = [item for item in plan.get("local_plans", []) if isinstance(item, dict)]
    if not isinstance(conflict_detection, dict) or not conflict_detection.get("enabled"):
        return {
            "ok": False,
            "error": "Protected bidirectional execution requires sync-dir conflict detection data.",
            "actions": [],
            "blocked": [],
            "skipped": [],
        }

    conflict_results_by_relative_path = {
        str(item.get("relative_path") or ""): item
        for item in conflict_detection.get("results", [])
        if isinstance(item, dict) and str(item.get("relative_path") or "")
    }
    risk_kinds_by_relative_path: Dict[str, List[str]] = {}
    for risk in plan.get("risks", []):
        if not isinstance(risk, dict):
            continue
        relative_path = str(risk.get("relative_path") or "")
        if not relative_path:
            continue
        risk_kinds_by_relative_path.setdefault(relative_path, []).append(str(risk.get("kind") or "risk"))

    actions: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    bidirectional_file_count = 0

    for local_plan in local_plans:
        relative_path = str(local_plan.get("relative_path") or "")
        sync_direction = normalize_sync_direction(local_plan.get("sync_direction"))
        if sync_direction != "bidirectional":
            continue
        bidirectional_file_count += 1

        doc_token = str(local_plan.get("doc_token") or "")
        if not doc_token:
            planned_action = str(local_plan.get("action") or "")
            if include_create_flow and planned_action in {"create_doc_in_root", "create_doc_in_folder"}:
                actions.append(
                    {
                        "mode": "create_push",
                        "relative_path": relative_path,
                        "doc_token": None,
                        "title": local_plan.get("title"),
                        "plan": local_plan,
                    }
                )
            else:
                blocked.append(
                    {
                        "relative_path": relative_path,
                        "doc_token": None,
                        "status": "missing_doc_token",
                        "recommended_action": "review_mapping",
                        "message": "This bidirectional file is not mapped to a Feishu doc token yet, so protected execution will not invent a new mapping or create a remote doc automatically unless --include-create-flow is enabled.",
                    }
                )
            continue

        conflict_result = conflict_results_by_relative_path.get(relative_path)
        if not isinstance(conflict_result, dict):
            blocked.append(
                {
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "status": "not_inspected",
                    "recommended_action": "review_remote_visibility",
                    "message": "This bidirectional file could not be inspected during sync-dir planning, so protected execution will not proceed.",
                    "risk_kinds": risk_kinds_by_relative_path.get(relative_path, []),
                }
            )
            continue

        if not conflict_result.get("ok"):
            blocked.append(
                {
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "status": str(conflict_result.get("status") or "inspect_failed"),
                    "recommended_action": str(conflict_result.get("recommended_action") or "review_remote_access"),
                    "message": "Remote inspection failed for this bidirectional file, so protected execution will not proceed.",
                    "inspection": conflict_result,
                }
            )
            continue

        comparison = conflict_result.get("comparison") if isinstance(conflict_result.get("comparison"), dict) else {}
        status = str(comparison.get("status") or "")
        if status == "local_ahead":
            actions.append(
                {
                    "mode": "push",
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "title": conflict_result.get("title") or local_plan.get("title"),
                    "plan": local_plan,
                    "inspection": conflict_result,
                }
            )
            continue
        if status == "remote_ahead":
            actions.append(
                {
                    "mode": "pull",
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "title": conflict_result.get("title") or local_plan.get("title"),
                    "plan": local_plan,
                    "inspection": conflict_result,
                }
            )
            continue
        if status == "local_and_remote_changed":
            merge_suggestion = conflict_result.get("merge_suggestion") if isinstance(conflict_result.get("merge_suggestion"), dict) else {}
            merged_body = extract_merged_body_text(merge_suggestion) if isinstance(merge_suggestion, dict) else None
            if (
                allow_auto_merge
                and merge_suggestion.get("ok")
                and merge_suggestion.get("auto_merge_ready")
                and isinstance(merged_body, str)
                and merged_body.strip()
            ):
                actions.append(
                    {
                        "mode": "merge_push",
                        "relative_path": relative_path,
                        "doc_token": doc_token,
                        "title": conflict_result.get("title") or local_plan.get("title"),
                        "plan": local_plan,
                        "inspection": conflict_result,
                        "merge_suggestion": merge_suggestion,
                    }
                )
                continue
        if status == "in_sync":
            skipped.append(
                {
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "status": status,
                    "message": str(comparison.get("message") or "The local and remote versions are already in sync."),
                }
            )
            continue

        blocked.append(
            {
                "relative_path": relative_path,
                "doc_token": doc_token,
                "status": status or "review_required",
                "recommended_action": str(comparison.get("recommended_action") or "manual_review"),
                "message": str(
                    comparison.get("message")
                    or "Protected bidirectional execution only proceeds when the file is cleanly local_ahead or remote_ahead."
                ),
                "inspection": conflict_result,
            }
        )

    remote_pull_candidates = [item for item in plan.get("remote_pull_candidates", []) if isinstance(item, dict)]
    if adopt_remote_new:
        for candidate in remote_pull_candidates:
            actions.append(
                {
                    "mode": "adopt_remote_pull",
                    "relative_path": str(candidate.get("relative_path") or ""),
                    "doc_token": str(candidate.get("doc_token") or ""),
                    "title": candidate.get("title"),
                    "candidate": candidate,
                }
            )

    summary = {
        "bidirectional_file_count": bidirectional_file_count,
        "actionable_count": len(actions),
        "push_count": sum(1 for item in actions if item.get("mode") == "push"),
        "pull_count": sum(1 for item in actions if item.get("mode") == "pull"),
        "merge_count": sum(1 for item in actions if item.get("mode") == "merge_push"),
        "create_count": sum(1 for item in actions if item.get("mode") == "create_push"),
        "adopt_count": sum(1 for item in actions if item.get("mode") == "adopt_remote_pull"),
        "push_like_count": sum(1 for item in actions if item.get("mode") in {"push", "merge_push", "create_push"}),
        "pull_like_count": sum(1 for item in actions if item.get("mode") in {"pull", "adopt_remote_pull"}),
        "blocked_count": len(blocked),
        "in_sync_count": len(skipped),
        "remote_candidate_count": len(remote_pull_candidates),
    }
    return {
        "ok": len(blocked) == 0,
        "summary": summary,
        "actions": actions,
        "blocked": blocked,
        "skipped": skipped,
    }


def execute_sync_dir_bidirectional(
    root: Path,
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    folder_token: Optional[str] = None,
    index_path: Optional[str] = None,
    recursive: bool = True,
    max_depth: int = 20,
    page_size: int = 100,
    max_pages: int = 20,
    backup_dir: Optional[str] = None,
    continue_on_error: bool = False,
    pull_fidelity: str = "low",
    allow_auto_merge: bool = False,
    adopt_remote_new: bool = False,
    include_create_flow: bool = False,
) -> Dict[str, Any]:
    plan = build_sync_dir_dry_run(
        root=root,
        tenant_access_token=tenant_access_token,
        base_url=base_url,
        timeout=timeout,
        folder_token=folder_token,
        index_path=index_path,
        recursive=recursive,
        max_depth=max_depth,
        page_size=page_size,
        max_pages=max_pages,
        prune=False,
        detect_conflicts=True,
        diff_fidelity="high" if allow_auto_merge else "low",
    )
    if not plan.get("ok"):
        return {
            "ok": False,
            "error": plan.get("error", "Failed to build the sync-dir bidirectional plan."),
            "plan": plan,
        }

    execution_plan = build_bidirectional_sync_execution_plan(
        plan,
        allow_auto_merge=allow_auto_merge,
        adopt_remote_new=adopt_remote_new,
        include_create_flow=include_create_flow,
    )
    resolved_root = Path(str(plan["root"])).resolve()
    effective_index_path = Path(str(plan["index_path"])).resolve()
    notes = [
        "Protected bidirectional execution only acts on bidirectional items that were classified into an explicit execution mode by sync-dir planning.",
        "The command blocks before any write when review-required, invisible, or incompletely mapped bidirectional files are still present.",
    ]
    if allow_auto_merge:
        notes.append(
            "With --allow-auto-merge, sync-dir may merge non-overlapping semantic block changes from a stored baseline snapshot before pushing the merged Markdown back to Feishu."
        )
    if adopt_remote_new:
        notes.append(
            "With --adopt-remote-new, visible unmapped remote docs become bidirectional pull targets and receive local Markdown files plus index mappings."
        )
    if include_create_flow:
        notes.append(
            "With --include-create-flow, unmapped local bidirectional files can create new remote Feishu docs during protected execution."
        )

    if not execution_plan.get("ok"):
        return {
            "ok": False,
            "root": str(resolved_root),
            "index_path": str(effective_index_path),
            "dry_run": False,
            "bidirectional": True,
            "summary": dict(plan.get("summary", {}), **execution_plan.get("summary", {}), failed_count=0),
            "local_plans": plan.get("local_plans", []),
            "remote_listing": plan.get("remote_listing", {}),
            "remote_pull_candidates": plan.get("remote_pull_candidates", []),
            "conflict_detection": plan.get("conflict_detection"),
            "execution_plan": execution_plan,
            "execution_results": [],
            "backup": None,
            "risks": plan.get("risks", []),
            "error": "Protected bidirectional execution was blocked because at least one bidirectional file still requires review or has an incomplete mapping.",
            "notes": notes + [
                "Re-run sync-dir with --dry-run --detect-conflicts --include-diff to review the blocked files before executing again.",
            ],
        }

    actions = [item for item in execution_plan.get("actions", []) if isinstance(item, dict)]
    if not actions:
        return {
            "ok": True,
            "root": str(resolved_root),
            "index_path": str(effective_index_path),
            "dry_run": False,
            "bidirectional": True,
            "summary": dict(plan.get("summary", {}), **execution_plan.get("summary", {}), failed_count=0),
            "local_plans": plan.get("local_plans", []),
            "remote_listing": plan.get("remote_listing", {}),
            "remote_pull_candidates": plan.get("remote_pull_candidates", []),
            "conflict_detection": plan.get("conflict_detection"),
            "execution_plan": execution_plan,
            "execution_results": [],
            "backup": None,
            "risks": plan.get("risks", []),
            "notes": notes + ["No actionable bidirectional push, pull, merge, create, or adopt candidates were found, so no writes were executed."],
        }

    backup_run_dir = resolve_sync_backup_run_dir(resolved_root, backup_dir, prefix="sync-dir-bidirectional")
    backup_plan_path = backup_run_dir / "sync-dir-plan.json"
    write_json_file(backup_plan_path, plan)
    execution_plan_path = backup_run_dir / "bidirectional-execution-plan.json"
    write_json_file(execution_plan_path, execution_plan)
    index_snapshot = backup_index_snapshot(effective_index_path, backup_run_dir)

    execution_results: List[Dict[str, Any]] = []
    pushed_relative_paths: List[str] = []
    pulled_relative_paths: List[str] = []
    merged_relative_paths: List[str] = []
    created_relative_paths: List[str] = []
    adopted_relative_paths: List[str] = []
    failed_count = 0

    for action in actions:
        relative_path = str(action.get("relative_path") or "")
        doc_token = str(action.get("doc_token") or "")
        title = str(action.get("title") or doc_token)
        local_plan = action.get("plan") if isinstance(action.get("plan"), dict) else {}
        action_mode = str(action.get("mode") or "")
        local_path = Path(str(local_plan.get("path") or resolved_root / relative_path)).resolve()

        if action_mode == "push":
            remote_backup = backup_remote_document_snapshot(
                candidate={
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "title": title,
                },
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                backup_run_dir=backup_run_dir,
                scope="remote-before-push",
                fidelity="high",
                backup_reason="sync-dir protected bidirectional push backup",
            )
            if not remote_backup.get("ok"):
                failed_count += 1
                execution_results.append(
                    {
                        "ok": False,
                        "mode": "push",
                        "relative_path": relative_path,
                        "doc_token": doc_token,
                        "title": title,
                        "backup": remote_backup,
                        "execute": None,
                    }
                )
                if not continue_on_error:
                    break
                continue

            push_result = execute_push_markdown(
                markdown_path=local_path,
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                root=resolved_root,
                index_path=str(effective_index_path),
                confirm_replace=True,
                ignore_sync_direction=True,
            )
            execution_results.append(
                {
                    "ok": bool(push_result.get("ok")),
                    "mode": "push",
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "title": title,
                    "backup": remote_backup,
                    "execute": push_result,
                }
            )
            if push_result.get("ok") and not push_result.get("skipped"):
                pushed_relative_paths.append(relative_path)
                continue

            failed_count += 1
            if not continue_on_error:
                break
            continue

        if action_mode == "merge_push":
            merge_suggestion = action.get("merge_suggestion") if isinstance(action.get("merge_suggestion"), dict) else {}
            local_backup = backup_local_markdown_snapshot(
                file_path=local_path,
                relative_path=relative_path,
                backup_run_dir=backup_run_dir,
                reason="sync-dir protected bidirectional merge local backup",
            )
            if not local_backup.get("ok"):
                failed_count += 1
                execution_results.append(
                    {
                        "ok": False,
                        "mode": "merge_push",
                        "relative_path": relative_path,
                        "doc_token": doc_token,
                        "title": title,
                        "backup": {"local": local_backup, "remote": None},
                        "execute": None,
                    }
                )
                if not continue_on_error:
                    break
                continue

            remote_backup = backup_remote_document_snapshot(
                candidate={
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "title": title,
                },
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                backup_run_dir=backup_run_dir,
                scope="remote-before-merge-push",
                fidelity="high",
                backup_reason="sync-dir protected bidirectional merge backup",
            )
            if not remote_backup.get("ok"):
                failed_count += 1
                execution_results.append(
                    {
                        "ok": False,
                        "mode": "merge_push",
                        "relative_path": relative_path,
                        "doc_token": doc_token,
                        "title": title,
                        "backup": {"local": local_backup, "remote": remote_backup},
                        "execute": None,
                    }
                )
                if not continue_on_error:
                    break
                continue

            merged_body = extract_merged_body_text(merge_suggestion)
            if not isinstance(merged_body, str) or not merged_body.strip():
                failed_count += 1
                execution_results.append(
                    {
                        "ok": False,
                        "mode": "merge_push",
                        "relative_path": relative_path,
                        "doc_token": doc_token,
                        "title": title,
                        "backup": {"local": local_backup, "remote": remote_backup},
                        "execute": None,
                        "error": "The semantic merge suggestion did not contain a reusable merged Markdown body.",
                    }
                )
                if not continue_on_error:
                    break
                continue

            local_merge_write = replace_markdown_body_preserving_front_matter(local_path, merged_body)
            if not local_merge_write.get("ok"):
                failed_count += 1
                execution_results.append(
                    {
                        "ok": False,
                        "mode": "merge_push",
                        "relative_path": relative_path,
                        "doc_token": doc_token,
                        "title": title,
                        "backup": {"local": local_backup, "remote": remote_backup},
                        "local_merge_write": local_merge_write,
                        "execute": None,
                    }
                )
                if not continue_on_error:
                    break
                continue

            push_result = execute_push_markdown(
                markdown_path=local_path,
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                root=resolved_root,
                index_path=str(effective_index_path),
                confirm_replace=True,
                ignore_sync_direction=True,
            )
            restore_result = None
            if not push_result.get("ok") or push_result.get("skipped"):
                backup_path = Path(str(local_backup.get("backup_path") or "")).resolve()
                try:
                    shutil.copy2(backup_path, local_path)
                    restore_result = {
                        "ok": True,
                        "path": str(local_path),
                        "backup_path": str(backup_path),
                    }
                except OSError as exc:
                    restore_result = {
                        "ok": False,
                        "path": str(local_path),
                        "backup_path": str(backup_path),
                        "error": str(exc),
                    }

            execution_results.append(
                {
                    "ok": bool(push_result.get("ok")) and not push_result.get("skipped"),
                    "mode": "merge_push",
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "title": title,
                    "backup": {"local": local_backup, "remote": remote_backup},
                    "local_merge_write": local_merge_write,
                    "restore_local": restore_result,
                    "execute": push_result,
                }
            )
            if push_result.get("ok") and not push_result.get("skipped"):
                pushed_relative_paths.append(relative_path)
                merged_relative_paths.append(relative_path)
                continue

            failed_count += 1
            if not continue_on_error:
                break
            continue

        if action_mode == "create_push":
            folder_token_override = str(local_plan.get("folder_token") or folder_token or "") or None
            push_result = execute_push_markdown(
                markdown_path=local_path,
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                root=resolved_root,
                index_path=str(effective_index_path),
                folder_token_override=folder_token_override,
                confirm_replace=False,
                ignore_sync_direction=True,
            )
            execution_results.append(
                {
                    "ok": bool(push_result.get("ok")) and not push_result.get("skipped"),
                    "mode": "create_push",
                    "relative_path": relative_path,
                    "doc_token": str(push_result.get("index_entry", {}).get("doc_token") or ""),
                    "title": title,
                    "backup": None,
                    "execute": push_result,
                }
            )
            if push_result.get("ok") and not push_result.get("skipped"):
                pushed_relative_paths.append(relative_path)
                created_relative_paths.append(relative_path)
                continue

            failed_count += 1
            if not continue_on_error:
                break
            continue

        if action_mode == "pull":
            local_backup = backup_local_markdown_snapshot(
                file_path=local_path,
                relative_path=relative_path,
                backup_run_dir=backup_run_dir,
                reason="sync-dir protected bidirectional pull backup",
            )
            if not local_backup.get("ok"):
                failed_count += 1
                execution_results.append(
                    {
                        "ok": False,
                        "mode": "pull",
                        "relative_path": relative_path,
                        "doc_token": doc_token,
                        "title": title,
                        "backup": local_backup,
                        "execute": None,
                    }
                )
                if not continue_on_error:
                    break
                continue

            pull_result = execute_pull_markdown(
                document_id=doc_token,
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                output_path=str(local_path),
                root=resolved_root,
                index_path=str(effective_index_path),
                overwrite=True,
                sync_direction="bidirectional",
                title_override=title,
                relative_path_hint=relative_path,
                write_index=True,
                fidelity=pull_fidelity,
            )
            execution_results.append(
                {
                    "ok": bool(pull_result.get("ok")),
                    "mode": "pull",
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "title": title,
                    "backup": local_backup,
                    "execute": pull_result,
                }
            )
            if pull_result.get("ok"):
                pulled_relative_paths.append(relative_path)
                continue

            failed_count += 1
            if not continue_on_error:
                break
            continue

        if action_mode == "adopt_remote_pull":
            candidate = action.get("candidate") if isinstance(action.get("candidate"), dict) else {}
            target_relative_path = str(candidate.get("relative_path") or relative_path)
            target_path = (resolved_root / target_relative_path).resolve()
            pull_result = execute_pull_markdown(
                document_id=doc_token,
                tenant_access_token=tenant_access_token,
                base_url=base_url,
                timeout=timeout,
                output_path=str(target_path),
                root=resolved_root,
                index_path=str(effective_index_path),
                overwrite=False,
                sync_direction="bidirectional",
                title_override=title,
                relative_path_hint=target_relative_path,
                write_index=True,
                fidelity=pull_fidelity,
            )
            execution_results.append(
                {
                    "ok": bool(pull_result.get("ok")),
                    "mode": "adopt_remote_pull",
                    "relative_path": target_relative_path,
                    "doc_token": doc_token,
                    "title": title,
                    "candidate": candidate,
                    "backup": None,
                    "execute": pull_result,
                }
            )
            if pull_result.get("ok"):
                pulled_relative_paths.append(target_relative_path)
                adopted_relative_paths.append(target_relative_path)
                continue

            failed_count += 1
            if not continue_on_error:
                break
            continue

        failed_count += 1
        execution_results.append(
            {
                "ok": False,
                "mode": action_mode or "unknown",
                "relative_path": relative_path,
                "doc_token": doc_token,
                "title": title,
                "backup": None,
                "execute": None,
                "error": "Unsupported bidirectional action mode.",
            }
        )
        if not continue_on_error:
            break

    summary = dict(plan.get("summary", {}))
    summary.update(
        {
            **execution_plan.get("summary", {}),
            "attempted_action_count": len(execution_results),
            "pushed_count": len(pushed_relative_paths),
            "pulled_count": len(pulled_relative_paths),
            "merged_count": len(merged_relative_paths),
            "created_count": len(created_relative_paths),
            "adopted_count": len(adopted_relative_paths),
            "failed_count": failed_count,
            "pull_fidelity": pull_fidelity,
        }
    )

    return {
        "ok": failed_count == 0,
        "root": str(resolved_root),
        "index_path": str(effective_index_path),
        "dry_run": False,
        "bidirectional": True,
        "summary": summary,
        "local_plans": plan.get("local_plans", []),
        "remote_listing": plan.get("remote_listing", {}),
        "remote_pull_candidates": plan.get("remote_pull_candidates", []),
        "conflict_detection": plan.get("conflict_detection"),
        "execution_plan": execution_plan,
        "execution_results": execution_results,
        "backup": {
            "run_dir": str(backup_run_dir),
            "plan_path": str(backup_plan_path),
            "execution_plan_path": str(execution_plan_path),
            "index_snapshot": index_snapshot,
        },
        "risks": plan.get("risks", []),
        "notes": notes
        + [
            "Each protected push backs up the current remote Feishu document before replace-markdown runs.",
            "Each protected pull backs up the current local Markdown file before pull-markdown overwrites it.",
            "Auto-merged files are restored from the local backup if the follow-up push fails after the merged Markdown body is written locally.",
        ],
    }


def execute_sync_dir_prune(
    root: Path,
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    folder_token: Optional[str] = None,
    index_path: Optional[str] = None,
    recursive: bool = True,
    max_depth: int = 20,
    page_size: int = 100,
    max_pages: int = 20,
    backup_dir: Optional[str] = None,
    continue_on_error: bool = False,
) -> Dict[str, Any]:
    plan = build_sync_dir_dry_run(
        root=root,
        tenant_access_token=tenant_access_token,
        base_url=base_url,
        timeout=timeout,
        folder_token=folder_token,
        index_path=index_path,
        recursive=recursive,
        max_depth=max_depth,
        page_size=page_size,
        max_pages=max_pages,
        prune=True,
    )
    if not plan.get("ok"):
        return {
            "ok": False,
            "error": plan.get("error", "Failed to build the sync-dir prune plan."),
            "plan": plan,
        }

    resolved_root = Path(str(plan["root"])).resolve()
    effective_index_path = Path(str(plan["index_path"])).resolve()
    prune_candidates = [
        dict(candidate)
        for candidate in plan.get("prune_candidates", [])
        if isinstance(candidate, dict)
    ]
    notes = [
        "sync-dir execution currently supports prune-only execution; mixed push or pull execution is still planned work.",
        "Every remote prune target is backed up locally before delete-document is attempted.",
    ]

    if not prune_candidates:
        return {
            "ok": True,
            "root": str(resolved_root),
            "index_path": str(effective_index_path),
            "dry_run": False,
            "prune": True,
            "summary": dict(plan.get("summary", {}), attempted_prune_count=0, pruned_count=0, failed_count=0, index_removed_count=0),
            "local_plans": plan.get("local_plans", []),
            "remote_listing": plan.get("remote_listing", {}),
            "remote_pull_candidates": plan.get("remote_pull_candidates", []),
            "prune_candidates": [],
            "prune_results": [],
            "risks": plan.get("risks", []),
            "backup": None,
            "index_cleanup": {
                "ok": True,
                "removed_count": 0,
                "removed_entries": [],
            },
            "notes": notes + ["No prune candidates were visible for this sync root, so no remote deletes were attempted."],
        }

    backup_run_dir = resolve_sync_backup_run_dir(resolved_root, backup_dir)
    backup_plan_path = backup_run_dir / "sync-dir-plan.json"
    write_json_file(backup_plan_path, plan)
    index_snapshot = backup_index_snapshot(effective_index_path, backup_run_dir)

    prune_results: List[Dict[str, Any]] = []
    deleted_relative_paths: List[str] = []
    deleted_doc_tokens: List[str] = []
    failed_count = 0

    for candidate in prune_candidates:
        relative_path = str(candidate.get("relative_path") or "")
        doc_token = str(candidate.get("doc_token") or "")
        title = str(candidate.get("title") or doc_token)
        backup_result = backup_remote_document_for_prune(
            candidate=candidate,
            tenant_access_token=tenant_access_token,
            base_url=base_url,
            timeout=timeout,
            backup_run_dir=backup_run_dir,
        )
        if not backup_result.get("ok"):
            failed_count += 1
            prune_results.append(
                {
                    "ok": False,
                    "relative_path": relative_path,
                    "doc_token": doc_token,
                    "title": title,
                    "action": "backup_before_prune",
                    "backup": backup_result,
                    "delete": None,
                    "index_cleanup": None,
                }
            )
            if not continue_on_error:
                break
            continue

        delete_result = delete_drive_file(
            tenant_access_token=tenant_access_token,
            file_token=doc_token,
            file_type="docx",
            base_url=base_url,
            timeout=timeout,
        )
        prune_results.append(
            {
                "ok": bool(delete_result.get("ok")),
                "relative_path": relative_path,
                "doc_token": doc_token,
                "title": title,
                "action": "prune_remote_doc",
                "backup": backup_result,
                "delete": delete_result,
                "index_cleanup": None,
            }
        )
        if delete_result.get("ok"):
            deleted_relative_paths.append(relative_path)
            deleted_doc_tokens.append(doc_token)
            continue

        failed_count += 1
        if not continue_on_error:
            break

    try:
        index_cleanup = (
            {
                "ok": True,
                **remove_index_entries(effective_index_path, deleted_relative_paths),
            }
            if deleted_relative_paths
            else {
                "ok": True,
                "removed_count": 0,
                "removed_entries": [],
            }
        )
    except OSError as exc:
        index_cleanup = {
            "ok": False,
            "removed_count": 0,
            "removed_entries": [],
            "error": str(exc),
        }

    if index_cleanup.get("ok"):
        removed_paths = {
            str(entry.get("relative_path") or "").replace("\\", "/").strip("/")
            for entry in index_cleanup.get("removed_entries", [])
            if isinstance(entry, dict)
        }
        for result in prune_results:
            relative_path = str(result.get("relative_path") or "").replace("\\", "/").strip("/")
            delete_result = result.get("delete")
            if (
                relative_path
                and relative_path in removed_paths
                and isinstance(delete_result, dict)
                and delete_result.get("ok")
            ):
                result["index_cleanup"] = "removed"
    else:
        failed_count += 1

    summary = dict(plan.get("summary", {}))
    summary.update(
        {
            "attempted_prune_count": len(prune_results),
            "pruned_count": len(deleted_relative_paths),
            "pruned_doc_tokens": deleted_doc_tokens,
            "failed_count": failed_count,
            "index_removed_count": index_cleanup.get("removed_count", 0),
        }
    )

    return {
        "ok": failed_count == 0 and bool(index_cleanup.get("ok")),
        "root": str(resolved_root),
        "index_path": str(effective_index_path),
        "dry_run": False,
        "prune": True,
        "summary": summary,
        "local_plans": plan.get("local_plans", []),
        "remote_listing": plan.get("remote_listing", {}),
        "remote_pull_candidates": plan.get("remote_pull_candidates", []),
        "prune_candidates": prune_candidates,
        "prune_results": prune_results,
        "risks": plan.get("risks", []),
        "backup": {
            "run_dir": str(backup_run_dir),
            "plan_path": str(backup_plan_path),
            "index_snapshot": index_snapshot,
        },
        "index_cleanup": index_cleanup,
        "notes": notes
        + [
            "The backup directory contains a sync-dir plan snapshot, an index snapshot, and one remote-doc backup folder per attempted prune target.",
            "Remote backups currently use the same low-fidelity raw_content export path as pull-markdown.",
        ],
    }


def read_markdown_file(path: Path) -> Tuple[Dict[str, Any], str, bool, str]:
    text = path.read_text(encoding="utf-8")
    front_matter, body, has_front_matter = split_front_matter(text)
    title = extract_title(front_matter, body, path)
    return front_matter, body, has_front_matter, title


def load_markdown_content(
    markdown_file: Optional[str],
    inline_content: Optional[str],
    keep_front_matter: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    if markdown_file and inline_content is not None:
        raise ValueError("Use either --markdown-file or --content, not both.")

    if markdown_file:
        path = Path(markdown_file).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Markdown file not found: {path}")
        text = path.read_text(encoding="utf-8")
        front_matter, body, has_front_matter = split_front_matter(text)
        content = text if keep_front_matter else body
        return content, {
            "source": "file",
            "path": str(path),
            "has_front_matter": has_front_matter,
            "front_matter_keys": sorted(front_matter.keys()),
        }

    if inline_content is not None:
        return inline_content, {
            "source": "inline",
            "path": None,
            "has_front_matter": False,
            "front_matter_keys": [],
        }

    raise ValueError("Missing Markdown input: use --markdown-file or --content.")


def resolve_mapping(
    front_matter: Dict[str, Any], index_entry: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    mapping: Dict[str, Any] = {}
    source: Dict[str, str] = {}

    field_aliases = {
        "doc_token": ("feishu_doc_token", "doc_token"),
        "folder_token": ("feishu_folder_token", "folder_token"),
        "wiki_node_token": ("feishu_wiki_node_token", "wiki_node_token"),
        "sync_direction": ("feishu_sync_direction", "sync_direction"),
        "title": ("title", "feishu_title"),
    }

    for target_field, aliases in field_aliases.items():
        for alias in aliases:
            value = front_matter.get(alias)
            if value not in (None, ""):
                mapping[target_field] = value
                source[target_field] = "front_matter"
                break

        if target_field not in mapping:
            index_alias = {
                "doc_token": "doc_token",
                "folder_token": "folder_token",
                "wiki_node_token": "wiki_node_token",
                "sync_direction": "sync_direction",
                "title": "title",
            }[target_field]
            value = index_entry.get(index_alias)
            if value not in (None, ""):
                mapping[target_field] = value
                source[target_field] = INDEX_FILENAME

    return mapping, source


def normalize_sync_direction(value: Any) -> str:
    if not isinstance(value, str):
        return "push"
    value = value.strip().lower()
    if value in VALID_SYNC_DIRECTIONS:
        return value
    return "push"


def plan_file(
    path: Path,
    mode: str,
    root: Optional[Path] = None,
    index_path: Optional[Path] = None,
) -> Dict[str, Any]:
    resolved_path = path.resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Markdown file not found: {resolved_path}")

    if index_path is None:
        index_path = discover_index_path(resolved_path)
    resolved_root = (root or (index_path.parent if index_path else resolved_path.parent)).resolve()
    if not resolved_root.is_dir():
        raise FileNotFoundError(f"Sync root not found: {resolved_root}")
    index_entries = load_index(index_path)

    front_matter, body, has_front_matter, title = read_markdown_file(resolved_path)
    relative_path = resolved_path.relative_to(resolved_root).as_posix()
    index_entry = index_entries.get(relative_path, {})
    mapping, mapping_source = resolve_mapping(front_matter, index_entry)

    doc_token = mapping.get("doc_token")
    folder_token = mapping.get("folder_token")
    wiki_node_token = mapping.get("wiki_node_token")
    sync_direction = normalize_sync_direction(mapping.get("sync_direction"))
    body_hash = sha256_text(body)

    warnings: List[str] = [
        "Use push-markdown or push-dir for tenant-mode execution after reviewing this plan."
    ]

    if mode == "push" and sync_direction == "pull":
        warnings.append("Front matter marks this file as pull-only, but the requested plan mode is push.")
    if mode == "pull" and sync_direction == "push":
        warnings.append("Front matter marks this file as push-only, but the requested plan mode is pull.")
    if mode == "pull" and not doc_token:
        warnings.append("Pull planning requires feishu_doc_token or an index doc_token mapping.")
    if not title:
        warnings.append("No title could be resolved from front matter, H1, or file name.")

    if mode == "push":
        if doc_token:
            action = "update_doc"
        elif wiki_node_token:
            action = "create_or_update_wiki_node"
        elif folder_token:
            action = "create_doc_in_folder"
        else:
            action = "create_doc_in_root"
    else:
        action = "pull_doc" if doc_token else "blocked_missing_doc_token"

    return {
        "mode": mode,
        "path": str(resolved_path),
        "root": str(resolved_root),
        "relative_path": relative_path,
        "title": title,
        "action": action,
        "content_hash": body_hash,
        "body_hash": body_hash,
        "has_front_matter": has_front_matter,
        "doc_token": doc_token,
        "folder_token": folder_token,
        "wiki_node_token": wiki_node_token,
        "sync_direction": sync_direction,
        "index_path": str(index_path.resolve()) if index_path else None,
        "mapping_source": mapping_source,
        "warnings": warnings,
    }


def iter_markdown_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for path in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def append_markdown_to_document(
    tenant_access_token: str,
    document_id: str,
    markdown_content: str,
    source_info: Dict[str, Any],
    base_url: str,
    timeout: int,
    document_revision_id: int = -1,
    parent_block_id: Optional[str] = None,
    user_id_type: Optional[str] = None,
    index: Optional[int] = None,
    client_token: Optional[str] = None,
    show_converted_blocks: bool = False,
) -> Dict[str, Any]:
    convert_result = convert_markdown_to_blocks(
        tenant_access_token=tenant_access_token,
        content=markdown_content,
        content_type="markdown",
        base_url=base_url,
        timeout=timeout,
        user_id_type=user_id_type,
    )
    if not convert_result["ok"]:
        return {
            "ok": False,
            "base_url": base_url,
            "official_docs": [
                OFFICIAL_REFERENCES["convert_markdown_html"],
                OFFICIAL_REFERENCES["create_descendant_blocks"],
            ],
            "source": source_info,
            "convert": convert_result,
        }

    create_result = create_descendant_blocks(
        tenant_access_token=tenant_access_token,
        document_id=document_id,
        block_id=parent_block_id or document_id,
        children_ids=list(convert_result["first_level_block_ids"]),
        descendants=list(convert_result["blocks"]),
        base_url=base_url,
        timeout=timeout,
        document_revision_id=document_revision_id,
        user_id_type=user_id_type,
        index=index,
        client_token=client_token or str(uuid.uuid4()),
    )

    response: Dict[str, Any] = {
        "ok": create_result["ok"],
        "base_url": base_url,
        "official_docs": [
            OFFICIAL_REFERENCES["convert_markdown_html"],
            OFFICIAL_REFERENCES["create_descendant_blocks"],
        ],
        "source": source_info,
        "request": {
            "document_id": document_id,
            "parent_block_id": parent_block_id or document_id,
            "document_revision_id": document_revision_id,
            "index": index,
            "user_id_type": user_id_type,
            "content_length": len(markdown_content),
            "content_hash": sha256_text(markdown_content),
        },
        "convert": {
            "ok": convert_result["ok"],
            "first_level_count": convert_result["first_level_count"],
            "block_count": convert_result["block_count"],
            "image_block_count": len(convert_result.get("block_id_to_image_urls", {})),
        },
        "write_result": create_result,
        "notes": [
            "This tenant write path appends converted Markdown blocks under the selected parent block.",
            "It does not replace or clear existing document content before writing.",
            "Table merge_info fields are stripped automatically before descendant block creation.",
        ],
    }
    if show_converted_blocks:
        response["convert"]["first_level_block_ids"] = convert_result["first_level_block_ids"]
        response["convert"]["blocks"] = convert_result["blocks"]
    return response


def replace_markdown_in_document(
    tenant_access_token: str,
    document_id: str,
    markdown_content: str,
    source_info: Dict[str, Any],
    base_url: str,
    timeout: int,
    document_revision_id: int = -1,
    user_id_type: Optional[str] = None,
    show_converted_blocks: bool = False,
) -> Dict[str, Any]:
    inspect_result = list_document_blocks(
        tenant_access_token=tenant_access_token,
        document_id=document_id,
        base_url=base_url,
        timeout=timeout,
        page_size=20,
        document_revision_id=document_revision_id,
    )
    if not inspect_result["ok"]:
        return {
            "ok": False,
            "base_url": base_url,
            "official_docs": [
                OFFICIAL_REFERENCES["list_document_blocks"],
                OFFICIAL_REFERENCES["delete_block_children"],
                OFFICIAL_REFERENCES["convert_markdown_html"],
                OFFICIAL_REFERENCES["create_descendant_blocks"],
            ],
            "source": source_info,
            "inspect": inspect_result,
        }

    items = inspect_result.get("items", [])
    root_block = next(
        (
            item
            for item in items
            if isinstance(item, dict) and str(item.get("block_id")) == document_id
        ),
        items[0] if items else None,
    )
    if not isinstance(root_block, dict):
        return {
            "ok": False,
            "base_url": base_url,
            "official_docs": [
                OFFICIAL_REFERENCES["list_document_blocks"],
                OFFICIAL_REFERENCES["delete_block_children"],
                OFFICIAL_REFERENCES["convert_markdown_html"],
                OFFICIAL_REFERENCES["create_descendant_blocks"],
            ],
            "source": source_info,
            "inspect": inspect_result,
            "error": "Could not resolve the root page block for replacement.",
        }

    children = root_block.get("children", [])
    child_count = len(children) if isinstance(children, list) else 0
    delete_result: Dict[str, Any]
    if child_count > 0:
        delete_result = delete_block_children(
            tenant_access_token=tenant_access_token,
            document_id=document_id,
            block_id=str(root_block.get("block_id") or document_id),
            start_index=0,
            end_index=child_count,
            base_url=base_url,
            timeout=timeout,
            document_revision_id=document_revision_id,
            client_token=str(uuid.uuid4()),
        )
        if not delete_result["ok"]:
            return {
                "ok": False,
                "base_url": base_url,
                "official_docs": [
                    OFFICIAL_REFERENCES["list_document_blocks"],
                    OFFICIAL_REFERENCES["delete_block_children"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                "source": source_info,
                "inspect": {
                    "root_block_id": root_block.get("block_id"),
                    "existing_child_count": child_count,
                },
                "delete": delete_result,
            }
    else:
        delete_result = {
            "kind": "docx_delete_block_children",
            "ok": True,
            "skipped": True,
            "document_id": document_id,
            "block_id": str(root_block.get("block_id") or document_id),
            "deleted_count": 0,
            "document_revision_id": document_revision_id,
        }

    append_response = append_markdown_to_document(
        tenant_access_token=tenant_access_token,
        document_id=document_id,
        markdown_content=markdown_content,
        source_info=source_info,
        base_url=base_url,
        timeout=timeout,
        document_revision_id=-1,
        parent_block_id=document_id,
        user_id_type=user_id_type,
        show_converted_blocks=show_converted_blocks,
    )

    return {
        "ok": append_response["ok"],
        "base_url": base_url,
        "official_docs": [
            OFFICIAL_REFERENCES["list_document_blocks"],
            OFFICIAL_REFERENCES["delete_block_children"],
            OFFICIAL_REFERENCES["convert_markdown_html"],
            OFFICIAL_REFERENCES["create_descendant_blocks"],
        ],
        "source": source_info,
        "inspect": {
            "root_block_id": root_block.get("block_id"),
            "existing_child_count": child_count,
            "has_more": inspect_result.get("has_more"),
        },
        "delete": delete_result,
        "append": append_response,
        "notes": [
            "replace-markdown clears the root page block children first, then appends converted Markdown blocks.",
            "This first version replaces only root-level document body content, not arbitrary nested parent blocks.",
        ],
    }


def execute_push_markdown(
    markdown_path: Path,
    tenant_access_token: str,
    base_url: str,
    timeout: int,
    root: Optional[Path] = None,
    index_path: Optional[str] = None,
    folder_token_override: Optional[str] = None,
    folder_token_fallback: Optional[str] = None,
    keep_front_matter: bool = False,
    confirm_replace: bool = False,
    ignore_sync_direction: bool = False,
    folder_resolution: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resolved_path = markdown_path.resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Markdown file not found: {resolved_path}")

    if root is not None:
        resolved_root = root.resolve()
    else:
        discovered_index_path = Path(index_path).resolve() if index_path else discover_index_path(resolved_path)
        resolved_root = (discovered_index_path.parent if discovered_index_path else resolved_path.parent).resolve()
    if not resolved_root.is_dir():
        raise FileNotFoundError(f"Sync root not found: {resolved_root}")

    if resolved_path.parent != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"Markdown file {resolved_path} is not under sync root {resolved_root}")

    effective_index_path = resolve_index_path(resolved_root, index_path)
    index_entries = load_index(effective_index_path)
    relative_path = resolved_path.relative_to(resolved_root).as_posix()

    front_matter, body, has_front_matter, title = read_markdown_file(resolved_path)
    source_info = {
        "source": "file",
        "path": str(resolved_path),
        "has_front_matter": has_front_matter,
        "front_matter_keys": sorted(front_matter.keys()),
    }
    markdown_content = resolved_path.read_text(encoding="utf-8")
    if not keep_front_matter and has_front_matter:
        markdown_content = body

    index_entry = index_entries.get(relative_path, {})
    mapping, mapping_source = resolve_mapping(front_matter, index_entry)
    doc_token = mapping.get("doc_token")
    explicit_folder_token = mapping.get("folder_token")
    if folder_token_override:
        folder_token = folder_token_override
    elif explicit_folder_token:
        folder_token = explicit_folder_token
    else:
        folder_token = folder_token_fallback
    wiki_node_token = mapping.get("wiki_node_token")
    sync_direction = normalize_sync_direction(mapping.get("sync_direction"))

    if not markdown_content.strip():
        return {
            "ok": False,
            "path": str(resolved_path),
            "relative_path": relative_path,
            "error": "Markdown input is empty after preprocessing.",
        }

    if not ignore_sync_direction and sync_direction == "pull":
        return {
            "ok": True,
            "skipped": True,
            "path": str(resolved_path),
            "relative_path": relative_path,
            "title": title,
            "sync_direction": sync_direction,
            "reason": "File is marked pull-only by front matter or index mapping.",
        }

    if wiki_node_token:
        return {
            "ok": False,
            "path": str(resolved_path),
            "relative_path": relative_path,
            "title": title,
            "sync_direction": sync_direction,
            "error": "Wiki-targeted push execution is not implemented yet in this scaffold.",
        }

    if doc_token and not confirm_replace:
        return {
            "ok": False,
            "path": str(resolved_path),
            "relative_path": relative_path,
            "title": title,
            "sync_direction": sync_direction,
            "error": "replace-markdown is destructive. Re-run with --confirm-replace to update an existing document.",
        }

    if doc_token:
        write_result = replace_markdown_in_document(
            tenant_access_token=tenant_access_token,
            document_id=str(doc_token),
            markdown_content=markdown_content,
            source_info=source_info,
            base_url=base_url,
            timeout=timeout,
        )
        action = "replace_doc"
        final_doc_token = str(doc_token)
    else:
        create_result = create_document(
            tenant_access_token=tenant_access_token,
            title=title,
            base_url=base_url,
            timeout=timeout,
            folder_token=str(folder_token) if folder_token else None,
        )
        if not create_result["ok"]:
            return {
                "ok": False,
                "path": str(resolved_path),
                "relative_path": relative_path,
                "title": title,
                "sync_direction": sync_direction,
                "action": "create_doc",
                "create": create_result,
            }
        final_doc_token = str(create_result["document_id"])
        append_result = append_markdown_to_document(
            tenant_access_token=tenant_access_token,
            document_id=final_doc_token,
            markdown_content=markdown_content,
            source_info=source_info,
            base_url=base_url,
            timeout=timeout,
            document_revision_id=-1,
        )
        write_result = {
            "ok": append_result["ok"],
            "create": create_result,
            "append": append_result,
        }
        action = "create_doc_and_append"

    if not write_result.get("ok"):
        return {
            "ok": False,
            "path": str(resolved_path),
            "relative_path": relative_path,
            "title": title,
            "sync_direction": sync_direction,
            "action": action,
            "write": write_result,
        }

    content_hash = sha256_text(markdown_content)
    body_hash = sha256_text(body)
    final_remote_revision_id = extract_final_document_revision_id(write_result)
    index_entry = update_index_entry(
        effective_index_path,
        relative_path,
        {
            "doc_token": final_doc_token,
            "title": title,
            "content_hash": content_hash,
            "body_hash": body_hash,
            "baseline_body_snapshot": encode_text_snapshot(body),
            "last_sync_at": current_timestamp_utc(),
            "sync_direction": sync_direction,
            "folder_token": str(folder_token) if folder_token else None,
            "remote_revision_id": final_remote_revision_id,
            "remote_content_hash": "",
            "last_sync_operation": "push",
        },
    )

    return {
        "ok": True,
        "path": str(resolved_path),
        "root": str(resolved_root),
        "relative_path": relative_path,
        "title": title,
        "action": action,
        "sync_direction": sync_direction,
        "folder_token": str(folder_token) if folder_token else None,
        "source": source_info,
        "mapping_source": mapping_source,
        "content_hash": content_hash,
        "body_hash": body_hash,
        "remote_revision_id": final_remote_revision_id,
        "index_path": str(effective_index_path),
        "index_entry": index_entry,
        "folder_resolution": folder_resolution,
        "write": write_result,
        "notes": [
            "push-markdown writes tenant-visible Markdown changes to Feishu and then updates feishu-index.json.",
            "Existing documents use replace-markdown; new documents use create-document plus append-markdown.",
        ],
    }


def command_doctor(_: argparse.Namespace) -> int:
    required_env = {name: bool(os.getenv(name)) for name in REQUIRED_ENV}
    token_env = {name: bool(os.getenv(name)) for name in OPTIONAL_TOKEN_ENV}
    optional_env = {name: bool(os.getenv(name)) for name in OPTIONAL_ENV}

    if token_env["FEISHU_TENANT_ACCESS_TOKEN"]:
        auth_strategy = "tenant_access_token_from_env"
    elif token_env["FEISHU_USER_ACCESS_TOKEN"]:
        auth_strategy = "user_access_token_from_env"
    elif all(required_env.values()):
        auth_strategy = "fetch_access_token_at_runtime"
    else:
        auth_strategy = "missing_app_credentials"

    notes = [
        "Feishu scope approval is not enough by itself; the app or user must also have access to the target document.",
        "For tenant_access_token flows, the target document usually needs the app added as a document app.",
        "For user_access_token flows, the backing user account must already have document access.",
    ]

    print_json(
        build_command_response(
            "doctor",
            True,
            mode="local",
            result={
                "required_env": required_env,
                "optional_env": optional_env,
                "token_env": token_env,
                "auth_strategy": auth_strategy,
                "recommended_scopes": RECOMMENDED_SCOPES,
                "token_docs": TOKEN_DOCS,
                "official_references": OFFICIAL_REFERENCES,
            },
            notes=notes,
        )
    )
    return 0


def command_scopes(_: argparse.Namespace) -> int:
    print_json(
        build_command_response(
            "scopes",
            True,
            mode="local",
            result={"recommended_scopes": RECOMMENDED_SCOPES},
            notes=[
                "Use docx:document as the simplest tenant-mode write scope.",
                "Add docx:document.block:convert whenever Markdown conversion is part of the flow.",
            ],
        )
    )
    return 0


def command_tenant_token(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        app_id = resolve_required_value(args, "app_id", "FEISHU_APP_ID")
        app_secret = resolve_required_value(args, "app_secret", "FEISHU_APP_SECRET")
    except ValueError as exc:
        print_json(
            build_command_response(
                "tenant-token",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"]],
                error=str(exc),
            )
        )
        return 1

    try:
        token_result = fetch_tenant_access_token(
            app_id=app_id,
            app_secret=app_secret,
            base_url=base_url,
            timeout=args.timeout,
        )
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "tenant-token",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"]],
                request={
                    "app_id": app_id,
                    "app_secret_preview": mask_secret(app_secret),
                    "show_token": bool(args.show_token),
                },
                error=str(exc),
            )
        )
        return 1

    result: Dict[str, Any] = {
        "status": token_result["status"],
        "code": token_result["code"],
        "msg": token_result["msg"],
    }

    if token_result["ok"]:
        result.update(
            {
                "expire": token_result["expire"],
                "tenant_access_token_preview": token_result["tenant_access_token_preview"],
                "app_access_token_preview": token_result["app_access_token_preview"],
            }
        )
        if args.show_token:
            result["tenant_access_token"] = token_result["tenant_access_token"]
        error = None
        notes = [
            "By default the CLI redacts tokens in output.",
            "Do not persist the tenant_access_token in the repository.",
        ]
    else:
        result.update(
            {
                "payload": token_result["payload"],
            }
        )
        error = "Failed to obtain tenant_access_token."
        notes = [
            "Check app credentials, network reachability, and Feishu tenant-token availability.",
        ]

    print_json(
        build_command_response(
            "tenant-token",
            token_result["ok"],
            mode="tenant",
            base_url=base_url,
            official_docs=[TOKEN_DOCS["tenant_access_token_internal"]],
            request={
                "app_id": app_id,
                "app_secret_preview": mask_secret(app_secret),
                "show_token": bool(args.show_token),
            },
            result=result,
            error=error,
            notes=notes,
        )
    )
    return 0 if token_result["ok"] else 1


def command_user_auth_url(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        app_id = resolve_required_value(args, "app_id", "FEISHU_APP_ID")
        redirect_uri = resolve_required_arg_or_env(
            args,
            "redirect_uri",
            "FEISHU_REDIRECT_URI",
            "--redirect-uri",
        )
    except ValueError as exc:
        print_json(
            build_command_response(
                "user-auth-url",
                False,
                mode="user",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["authorization_code_guide"],
                    TOKEN_DOCS["authorize_login_guide"],
                    TOKEN_DOCS["user_access_token"],
                ],
                error=str(exc),
            )
        )
        return 1

    state = args.state or secrets.token_urlsafe(18)
    auth_url = build_user_auth_url(
        app_id=app_id,
        redirect_uri=redirect_uri,
        base_url=base_url,
        state=state,
        scope=args.scope,
    )
    print_json(
        build_command_response(
            "user-auth-url",
            True,
            mode="user",
            base_url=base_url,
            official_docs=[
                TOKEN_DOCS["authorization_code_guide"],
                TOKEN_DOCS["authorize_login_guide"],
                TOKEN_DOCS["user_access_token"],
            ],
            request={
                "app_id": app_id,
                "redirect_uri": redirect_uri,
                "scope": args.scope,
                "state": state,
            },
            result={
                "authorization_url": auth_url,
            },
            notes=[
                "This first version defaults to the live authorize endpoint /open-apis/authen/v1/authorize.",
                "The redirect_uri must exactly match the value configured for the Feishu app login flow.",
                "The authorization code is only valid for 5 minutes according to the official Feishu OAuth docs.",
                "After the browser redirects back with a code, run exchange-user-token with the same redirect_uri.",
            ],
        )
    )
    return 0


def command_exchange_user_token(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        app_id = resolve_required_value(args, "app_id", "FEISHU_APP_ID")
        app_secret = resolve_required_value(args, "app_secret", "FEISHU_APP_SECRET")
        redirect_uri = resolve_required_arg_or_env(
            args,
            "redirect_uri",
            "FEISHU_REDIRECT_URI",
            "--redirect-uri",
        )
    except ValueError as exc:
        print_json(
            build_command_response(
                "exchange-user-token",
                False,
                mode="user",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "exchange-user-token",
                False,
                mode="user",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                error=str(exc),
            )
        )
        return 1

    result = exchange_user_access_token(
        app_id=app_id,
        app_secret=app_secret,
        code=args.code,
        redirect_uri=redirect_uri,
        base_url=base_url,
        timeout=get_request_timeout(args),
    )
    result_payload: Dict[str, Any] = {
        "exchange": {
            "kind": result["kind"],
            "ok": result["ok"],
            "status": result["status"],
            "code": result["code"],
            "message": result["message"],
        }
    }

    if result["ok"]:
        result_payload["token_bundle"] = redact_sensitive_payload(result["token_bundle"])
        notes = [
            "Token fields are redacted by default.",
            "Persist user_access_token and refresh_token only in a secure local secret store.",
            "This flow exchanges the 5-minute authorization code directly with client_id and client_secret.",
        ]
        if args.show_tokens:
            result_payload["token_bundle"] = result["token_bundle"]
        error = None
    else:
        result_payload["error_payload"] = redact_sensitive_payload(result.get("payload"))
        notes = [
            "A redirect_uri mismatch is one of the most common reasons for exchange failure.",
            "Authorization codes are single-use and expire after 5 minutes.",
            "Use the same redirect_uri value for user-auth-url and exchange-user-token.",
        ]
        error = "Failed to exchange authorization code for user_access_token."

    print_json(
        build_command_response(
            "exchange-user-token",
            result["ok"],
            mode="user",
            base_url=base_url,
            official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
            request={
                "grant_type": "authorization_code",
                "client_id": app_id,
                "code_preview": preview_token(args.code),
                "redirect_uri": redirect_uri,
                "show_tokens": bool(args.show_tokens),
            },
            result=result_payload,
            error=error,
            notes=notes,
        )
    )
    return 0 if result["ok"] else 1


def command_authorize_local(args: argparse.Namespace) -> int:
    host = args.host
    callback_path = normalize_callback_path(args.callback_path)
    wait_timeout = max(1, int(args.timeout))
    base_url = normalize_base_url(args.base_url)

    try:
        app_id = resolve_required_value(args, "app_id", "FEISHU_APP_ID")
        app_secret = resolve_required_value(args, "app_secret", "FEISHU_APP_SECRET")
    except ValueError as exc:
        print_json(
            build_command_response(
                "authorize-local",
                False,
                mode="user",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "authorize-local",
                False,
                mode="user",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                error=str(exc),
            )
        )
        return 1

    try:
        server, callback_result = start_local_oauth_callback_server(
            host=host,
            port=args.port,
            callback_path=callback_path,
        )
    except OSError as exc:
        print_json(
            build_command_response(
                "authorize-local",
                False,
                mode="user",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                request={
                    "host": host,
                    "port": args.port,
                    "callback_path": callback_path,
                    "scope": args.scope,
                    "no_open_browser": bool(args.no_open_browser),
                },
                error=f"Failed to bind local callback server on {host}:{args.port}: {exc}",
            )
        )
        return 1

    actual_host, actual_port = server.server_address
    redirect_uri = build_local_redirect_uri(str(actual_host), int(actual_port), callback_path)
    state = args.state or secrets.token_urlsafe(18)
    authorization_url = build_user_auth_url(
        app_id=app_id,
        redirect_uri=redirect_uri,
        base_url=base_url,
        state=state,
        scope=args.scope,
    )
    request_payload = {
        "app_id": app_id,
        "redirect_uri": redirect_uri,
        "host": str(actual_host),
        "port": int(actual_port),
        "callback_path": callback_path,
        "scope": args.scope,
        "state": state,
        "no_open_browser": bool(args.no_open_browser),
    }

    browser_opened = False
    browser_error: Optional[str] = None
    if not args.no_open_browser:
        try:
            browser_opened = bool(webbrowser.open(authorization_url))
        except Exception as exc:  # pragma: no cover - platform-specific browser integration
            browser_error = str(exc)

    if not browser_opened and args.no_open_browser:
        print(f"Open this URL in a browser to continue: {authorization_url}", flush=True)
    elif not browser_opened:
        print(
            "Browser auto-open was unavailable. Open this URL manually:\n"
            f"{authorization_url}",
            flush=True,
        )

    print(
        f"Waiting for Feishu authorization callback on {redirect_uri} "
        f"(timeout: {wait_timeout}s)",
        flush=True,
    )

    try:
        received = callback_result.event.wait(wait_timeout)
        if not received:
            print_json(
                build_command_response(
                    "authorize-local",
                    False,
                    mode="user",
                    base_url=base_url,
                    official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                    request=request_payload,
                    result={
                        "authorization_url": authorization_url,
                        "browser_opened": browser_opened,
                        "browser_error": browser_error,
                    },
                    error=f"Timed out waiting for the local callback after {wait_timeout} seconds.",
                    notes=[
                        "The default wait window is 300 seconds so it matches Feishu's 5-minute authorization-code lifetime.",
                        "Configure the same redirect URI in the Feishu app login settings before retrying.",
                        "You can rerun this command with --no-open-browser if you want to open the URL yourself.",
                    ],
                )
            )
            return 1

        callback_query = callback_result.query
        callback_payload = redact_sensitive_payload(callback_query)

        if callback_query.get("state") != state:
            print_json(
                build_command_response(
                    "authorize-local",
                    False,
                    mode="user",
                    base_url=base_url,
                    official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                    request=request_payload,
                    result={
                        "authorization_url": authorization_url,
                        "callback_query": callback_payload,
                        "browser_opened": browser_opened,
                        "browser_error": browser_error,
                    },
                    error="State mismatch in the local OAuth callback.",
                    notes=["Discard the callback and start a new OAuth flow when the returned state does not match."],
                    extras={"expected_state": state},
                )
            )
            return 1

        if "error" in callback_query:
            print_json(
                build_command_response(
                    "authorize-local",
                    False,
                    mode="user",
                    base_url=base_url,
                    official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                    request=request_payload,
                    result={
                        "authorization_url": authorization_url,
                        "callback_query": callback_payload,
                        "browser_opened": browser_opened,
                        "browser_error": browser_error,
                    },
                    error="Feishu returned an OAuth error in the local callback.",
                )
            )
            return 1

        code = callback_query.get("code")
        if not code:
            print_json(
                build_command_response(
                    "authorize-local",
                    False,
                    mode="user",
                    base_url=base_url,
                    official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                    request=request_payload,
                    result={
                        "authorization_url": authorization_url,
                        "callback_query": callback_payload,
                        "browser_opened": browser_opened,
                        "browser_error": browser_error,
                    },
                    error="The local callback did not include a code parameter.",
                )
            )
            return 1

        result = exchange_user_access_token(
            app_id=app_id,
            app_secret=app_secret,
            code=code,
            redirect_uri=redirect_uri,
            base_url=base_url,
            timeout=get_request_timeout(args),
        )
        result_payload: Dict[str, Any] = {
            "authorization_url": authorization_url,
            "browser_opened": browser_opened,
            "browser_error": browser_error,
            "callback_query": callback_payload,
            "exchange": {
                "kind": result["kind"],
                "ok": result["ok"],
                "status": result["status"],
                "code": result["code"],
                "message": result["message"],
            },
        }

        if result["ok"]:
            result_payload["token_bundle"] = redact_sensitive_payload(result["token_bundle"])
            notes = [
                "The browser callback was received locally, so no manual code copy was needed.",
                "Token fields are redacted by default.",
                "The default 300-second wait matches Feishu's documented 5-minute authorization-code lifetime.",
            ]
            if args.show_tokens:
                result_payload["token_bundle"] = result["token_bundle"]
            error = None
        else:
            result_payload["error_payload"] = redact_sensitive_payload(result.get("payload"))
            notes = [
                "A redirect_uri mismatch is one of the most common reasons for exchange failure.",
                "Authorization codes are single-use and expire after 5 minutes.",
                "Configure the same redirect URI in the Feishu app login settings before retrying.",
            ]
            error = "Failed to exchange authorization code for user_access_token after receiving the local callback."

        print_json(
            build_command_response(
                "authorize-local",
                result["ok"],
                mode="user",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["authorization_code_guide"], TOKEN_DOCS["user_access_token"]],
                request=request_payload,
                result=result_payload,
                error=error,
                notes=notes,
            )
        )
        return 0 if result["ok"] else 1
    finally:
        server.shutdown()
        server.server_close()


def command_validate_tenant(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "validate-tenant",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_document"]],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "validate-tenant",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_document"]],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    result: Dict[str, Any] = {
        "probe": None,
    }
    notes = [
            "Auth success proves the app_id and app_secret can reach Feishu auth successfully.",
            "Doc API success still depends on scopes and document-level sharing.",
    ]

    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "validate-tenant",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_document"]],
                request={"document_id": args.document_id or args.doc_token},
                auth=auth,
                result=result,
                error="Failed to resolve tenant_access_token for validation.",
                notes=notes,
            )
        )
        return 1

    document_id = args.document_id or args.doc_token
    if document_id:
        probe = probe_document_connectivity(
            tenant_access_token=str(token_result["tenant_access_token"]),
            document_id=document_id,
            base_url=base_url,
            timeout=args.timeout,
        )
        result["probe"] = probe
        ok = bool(probe["ok"])
        if not probe["ok"]:
            notes.append(
                "If auth succeeded but doc probing failed, check doc scopes and whether the app has been added to the target document."
            )
    else:
        result["probe"] = {
            "kind": "auth_only",
            "ok": True,
            "msg": "tenant_access_token acquired successfully. No docx probe was attempted because no --document-id was provided.",
        }
        ok = True

    print_json(
        build_command_response(
            "validate-tenant",
            ok,
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_document"]],
            request={"document_id": document_id},
            auth=auth,
            result=result,
            error=None if ok else "Tenant auth succeeded, but the document connectivity probe failed.",
            notes=notes,
        )
    )
    return 0 if ok else 1


def command_create_document(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "create-document",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["create_document"]],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "create-document",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["create_document"]],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "create-document",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["create_document"]],
                request={"title": args.title.strip(), "folder_token": args.folder_token},
                auth=auth,
                error="Failed to resolve tenant_access_token for create-document.",
            )
        )
        return 1

    title = args.title.strip()
    result = create_document(
        tenant_access_token=str(token_result["tenant_access_token"]),
        title=title,
        folder_token=args.folder_token,
        base_url=base_url,
        timeout=args.timeout,
    )
    print_json(
        build_command_response(
            "create-document",
            result["ok"],
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["create_document"]],
            request={
                "title": title,
                "folder_token": args.folder_token,
            },
            auth=auth,
            result=result,
            error=None if result["ok"] else "Failed to create the Feishu cloud document.",
            notes=[
            "A successful create-document call creates a real Feishu cloud document.",
            "If folder_token is omitted, Feishu uses the app's default creation behavior for the current token type.",
            ],
        )
    )
    return 0 if result["ok"] else 1


def command_get_document(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "get-document",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_document"]],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "get-document",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_document"]],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "get-document",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_document"]],
                request={"document_id": args.document_id},
                auth=auth,
                error="Failed to resolve tenant_access_token for get-document.",
            )
        )
        return 1

    result = probe_document_connectivity(
        tenant_access_token=str(token_result["tenant_access_token"]),
        document_id=args.document_id,
        base_url=base_url,
        timeout=args.timeout,
    )
    print_json(
        build_command_response(
            "get-document",
            result["ok"],
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_document"]],
            request={"document_id": args.document_id},
            auth=auth,
            result=result,
            error=None if result["ok"] else "Failed to read Feishu document metadata.",
        )
    )
    return 0 if result["ok"] else 1


def command_get_raw_content(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "get-raw-content",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_raw_content"]],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "get-raw-content",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_raw_content"]],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "get-raw-content",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_raw_content"]],
                request={"document_id": args.document_id},
                auth=auth,
                error="Failed to resolve tenant_access_token for get-raw-content.",
            )
        )
        return 1

    result = get_document_raw_content(
        tenant_access_token=str(token_result["tenant_access_token"]),
        document_id=args.document_id,
        base_url=base_url,
        timeout=args.timeout,
    )
    print_json(
        build_command_response(
            "get-raw-content",
            result["ok"],
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["get_raw_content"]],
            request={"document_id": args.document_id},
            auth=auth,
            result=result,
            error=None if result["ok"] else "Failed to read Feishu raw document content.",
            notes=[
            "This command reads the plain-text view returned by the Feishu docx raw_content API.",
            "The plain-text response is useful for drift checks and simple sync verification, but it is not a lossless block-model export.",
            ],
        )
    )
    return 0 if result["ok"] else 1


def command_upload_media(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    request_payload = {
        "document_id": args.document_id,
        "path": str(Path(args.path).resolve()),
        "parent_type": args.parent_type,
        "file_name": args.file_name,
        "extra_drive_route_token": args.extra_drive_route_token,
    }
    official_docs = [
        TOKEN_DOCS["tenant_access_token_internal"],
        OFFICIAL_REFERENCES["upload_media"],
    ]
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "upload-media",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "upload-media",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "upload-media",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=request_payload,
                auth=auth,
                error="Failed to resolve tenant_access_token for upload-media.",
            )
        )
        return 1

    try:
        result = upload_document_media(
            tenant_access_token=str(token_result["tenant_access_token"]),
            document_id=args.document_id,
            file_path=Path(args.path),
            base_url=base_url,
            timeout=args.timeout,
            parent_type=args.parent_type,
            file_name=args.file_name,
            extra_drive_route_token=args.extra_drive_route_token,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print_json(
            build_command_response(
                "upload-media",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=request_payload,
                auth=auth,
                error=str(exc),
            )
        )
        return 1

    print_json(
        build_command_response(
            "upload-media",
            result["ok"],
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=official_docs,
            request=request_payload,
            auth=auth,
            result=result,
            error=None if result["ok"] else "Failed to upload media into the Feishu document context.",
            notes=[
                "upload-media performs a real multipart upload and returns the media file_token from Feishu.",
                "Use parent_type=docx_image for document images; later Markdown-to-docx media wiring can reuse the returned token.",
            ],
        )
    )
    return 0 if result["ok"] else 1


def command_list_root_files(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "list-root-files",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["root_folder_meta"],
                    OFFICIAL_REFERENCES["list_drive_files"],
                ],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "list-root-files",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["root_folder_meta"],
                    OFFICIAL_REFERENCES["list_drive_files"],
                ],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "list-root-files",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["root_folder_meta"],
                    OFFICIAL_REFERENCES["list_drive_files"],
                ],
                request={
                    "folder_token": args.folder_token,
                    "page_size": args.page_size,
                    "one_page": bool(args.one_page),
                    "max_pages": args.max_pages,
                },
                auth=auth,
                error="Failed to resolve tenant_access_token for list-root-files.",
            )
        )
        return 1

    root_result = get_root_folder_meta(
        tenant_access_token=str(token_result["tenant_access_token"]),
        base_url=base_url,
        timeout=args.timeout,
    )
    if not root_result["ok"]:
        print_json(
            build_command_response(
                "list-root-files",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["root_folder_meta"],
                    OFFICIAL_REFERENCES["list_drive_files"],
                ],
                request={
                    "folder_token": args.folder_token,
                    "page_size": args.page_size,
                    "one_page": bool(args.one_page),
                    "max_pages": args.max_pages,
                },
                auth=auth,
                result={"root_folder": root_result},
                error="Failed to resolve the Feishu drive root folder metadata.",
            )
        )
        return 1

    root_token = args.folder_token or root_result["token"]
    page_count = 0
    page_token: Optional[str] = None
    files: List[Dict[str, Any]] = []
    pages: List[Dict[str, Any]] = []

    while True:
        page_count += 1
        page_result = list_drive_files(
            tenant_access_token=str(token_result["tenant_access_token"]),
            base_url=base_url,
            timeout=args.timeout,
            folder_token=root_token,
            page_size=args.page_size,
            page_token=page_token,
        )
        pages.append(
            {
                "page": page_count,
                "ok": page_result["ok"],
                "status": page_result["status"],
                "code": page_result["code"],
                "msg": page_result["msg"],
                "count": page_result["count"],
                "has_more": page_result["has_more"],
                "next_page_token": page_result["next_page_token"],
            }
        )
        if not page_result["ok"]:
            print_json(
                build_command_response(
                    "list-root-files",
                    False,
                    mode="tenant",
                    base_url=base_url,
                    token_source=token_result.get("source"),
                    official_docs=[
                        TOKEN_DOCS["tenant_access_token_internal"],
                        OFFICIAL_REFERENCES["root_folder_meta"],
                        OFFICIAL_REFERENCES["list_drive_files"],
                    ],
                    request={
                        "folder_token": args.folder_token,
                        "page_size": args.page_size,
                        "one_page": bool(args.one_page),
                        "max_pages": args.max_pages,
                    },
                    auth=auth,
                    result={
                        "root_folder": root_result,
                        "pages": pages,
                        "failed_page": page_result,
                    },
                    error="Failed while listing drive files from the resolved root folder.",
                )
            )
            return 1

        files.extend(page_result["files"])

        if args.one_page or not page_result["has_more"]:
            break

        page_token = page_result["next_page_token"]
        if not page_token or page_count >= args.max_pages:
            break

    print_json(
        build_command_response(
            "list-root-files",
            True,
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[
                TOKEN_DOCS["tenant_access_token_internal"],
                OFFICIAL_REFERENCES["root_folder_meta"],
                OFFICIAL_REFERENCES["list_drive_files"],
            ],
            request={
                "folder_token": args.folder_token,
                "page_size": args.page_size,
                "one_page": bool(args.one_page),
                "max_pages": args.max_pages,
            },
            auth=auth,
            result={
                "root_folder": root_result,
                "page_count": page_count,
                "file_count": len(files),
                "files": files,
                "pages": pages,
            },
            notes=[
                "This command lists files visible to the current token under the resolved root folder token.",
                "If expected files are missing, the app likely does not have document-level access to them yet.",
            ],
        )
    )
    return 0


def command_list_folder_files(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "list-folder-files",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["root_folder_meta"],
                    OFFICIAL_REFERENCES["list_drive_files"],
                ],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "list-folder-files",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["root_folder_meta"],
                    OFFICIAL_REFERENCES["list_drive_files"],
                ],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "list-folder-files",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["root_folder_meta"],
                    OFFICIAL_REFERENCES["list_drive_files"],
                ],
                request={
                    "folder_token": args.folder_token,
                    "recursive": bool(args.recursive),
                    "max_depth": args.max_depth,
                    "page_size": args.page_size,
                    "max_pages": args.max_pages,
                },
                auth=auth,
                error="Failed to resolve tenant_access_token for list-folder-files.",
            )
        )
        return 1

    result = list_drive_folder_contents(
        tenant_access_token=str(token_result["tenant_access_token"]),
        base_url=base_url,
        timeout=args.timeout,
        folder_token=args.folder_token,
        recursive=args.recursive,
        max_depth=args.max_depth,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )
    print_json(
        build_command_response(
            "list-folder-files",
            result["ok"],
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[
                TOKEN_DOCS["tenant_access_token_internal"],
                OFFICIAL_REFERENCES["root_folder_meta"],
                OFFICIAL_REFERENCES["list_drive_files"],
            ],
            request={
                "folder_token": args.folder_token,
                "recursive": bool(args.recursive),
                "max_depth": args.max_depth,
                "page_size": args.page_size,
                "max_pages": args.max_pages,
            },
            auth=auth,
            result=result,
            error=None if result["ok"] else result.get("error", "Failed to list the requested drive folder."),
            notes=[
                "This command can enumerate a specific folder token or fall back to the app-visible root folder.",
                "Use --recursive to walk nested folders and surface docx files beyond one level.",
            ],
        )
    )
    return 0 if result["ok"] else 1


def command_delete_document(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "delete-document",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["delete_file"]],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "delete-document",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["delete_file"]],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "delete-document",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["delete_file"]],
                request={
                    "document_id": args.document_id,
                    "file_type": args.file_type,
                },
                auth=auth,
                error="Failed to resolve tenant_access_token for delete-document.",
            )
        )
        return 1

    result = delete_drive_file(
        tenant_access_token=str(token_result["tenant_access_token"]),
        file_token=args.document_id,
        file_type=args.file_type,
        base_url=base_url,
        timeout=args.timeout,
    )
    print_json(
        build_command_response(
            "delete-document",
            result["ok"],
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[TOKEN_DOCS["tenant_access_token_internal"], OFFICIAL_REFERENCES["delete_file"]],
            request={
                "document_id": args.document_id,
                "file_type": args.file_type,
            },
            auth=auth,
            result=result,
            error=None if result["ok"] else "Failed to delete the Feishu drive file.",
            notes=[
            "This command performs a real delete against the Feishu drive file API.",
            "Use it carefully: successful deletes affect the remote cloud document immediately.",
            ],
        )
    )
    return 0 if result["ok"] else 1


def command_pull_markdown(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    official_docs = [
        TOKEN_DOCS["tenant_access_token_internal"],
        OFFICIAL_REFERENCES["get_document"],
        OFFICIAL_REFERENCES["get_raw_content"],
    ]
    if args.fidelity == "high":
        official_docs = normalize_reference_list(official_docs, [OFFICIAL_REFERENCES["list_document_blocks"]])
    request_payload = {
        "document_id": args.document_id,
        "output": args.output,
        "root": args.root,
        "index_path": args.index_path,
        "overwrite": bool(args.overwrite),
        "sync_direction": args.sync_direction,
        "title": args.title,
        "folder_token": args.folder_token,
        "relative_path": args.relative_path,
        "write_index": bool(args.write_index or args.root or args.index_path),
        "fidelity": args.fidelity,
    }
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "pull-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "pull-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "pull-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=request_payload,
                auth=auth,
                error="Failed to resolve tenant_access_token for pull-markdown.",
            )
        )
        return 1

    try:
        result = execute_pull_markdown(
            document_id=args.document_id,
            tenant_access_token=str(token_result["tenant_access_token"]),
            base_url=base_url,
            timeout=args.timeout,
            output_path=args.output,
            root=Path(args.root).resolve() if args.root else None,
            index_path=args.index_path,
            overwrite=args.overwrite,
            sync_direction=args.sync_direction,
            title_override=args.title,
            folder_token=args.folder_token,
            relative_path_hint=args.relative_path,
            write_index=bool(args.write_index or args.root or args.index_path),
            fidelity=args.fidelity,
        )
    except (ValueError, FileNotFoundError, OSError) as exc:
        print_json(
            build_command_response(
                "pull-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=request_payload,
                auth=auth,
                error=str(exc),
            )
        )
        return 1

    result_payload = dict(result)
    notes = result_payload.pop("notes", [])
    print_json(
        build_command_response(
            "pull-markdown",
            result["ok"],
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=official_docs,
            request=request_payload,
            auth=auth,
            result=result_payload,
            error=None if result["ok"] else result.get("error", "Failed to pull the Feishu document into local Markdown."),
            notes=notes,
        )
    )
    return 0 if result["ok"] else 1


def command_append_markdown(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
        markdown_content, source_info = load_markdown_content(
            markdown_file=args.markdown_file,
            inline_content=args.content,
            keep_front_matter=args.keep_front_matter,
        )
    except ValueError as exc:
        print_json(
            build_command_response(
                "append-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                error=str(exc),
            )
        )
        return 1
    except FileNotFoundError as exc:
        print_json(
            build_command_response(
                "append-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "append-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "append-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                request={
                    "document_id": args.document_id,
                    "document_revision_id": args.document_revision_id,
                    "parent_block_id": args.parent_block_id,
                    "user_id_type": args.user_id_type,
                    "index": args.index,
                    "client_token": args.client_token,
                    "keep_front_matter": bool(args.keep_front_matter),
                    "show_converted_blocks": bool(args.show_converted_blocks),
                },
                auth=auth,
                error="Failed to resolve tenant_access_token for append-markdown.",
            )
        )
        return 1

    if not markdown_content.strip():
        print_json(
            build_command_response(
                "append-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                request={
                    "document_id": args.document_id,
                    "keep_front_matter": bool(args.keep_front_matter),
                },
                auth=auth,
                error="Markdown input is empty after preprocessing.",
            )
        )
        return 1

    response = append_markdown_to_document(
        tenant_access_token=str(token_result["tenant_access_token"]),
        document_id=args.document_id,
        markdown_content=markdown_content,
        source_info=source_info,
        base_url=base_url,
        timeout=args.timeout,
        document_revision_id=args.document_revision_id,
        parent_block_id=args.parent_block_id,
        user_id_type=args.user_id_type,
        index=args.index,
        client_token=args.client_token,
        show_converted_blocks=args.show_converted_blocks,
    )
    response["token_source"] = token_result.get("source")
    result_payload = dict(response)
    notes = result_payload.pop("notes", [])
    print_json(
        build_command_response(
            "append-markdown",
            response["ok"],
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[
                TOKEN_DOCS["tenant_access_token_internal"],
                OFFICIAL_REFERENCES["convert_markdown_html"],
                OFFICIAL_REFERENCES["create_descendant_blocks"],
            ],
            request={
                "document_id": args.document_id,
                "document_revision_id": args.document_revision_id,
                "parent_block_id": args.parent_block_id,
                "user_id_type": args.user_id_type,
                "index": args.index,
                "client_token": args.client_token,
                "keep_front_matter": bool(args.keep_front_matter),
                "show_converted_blocks": bool(args.show_converted_blocks),
                "markdown_source": source_info,
            },
            auth=auth,
            result=result_payload,
            error=None if response["ok"] else "Failed to append converted Markdown to the Feishu document.",
            notes=notes,
        )
    )
    return 0 if response["ok"] else 1


def command_replace_markdown(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
        markdown_content, source_info = load_markdown_content(
            markdown_file=args.markdown_file,
            inline_content=args.content,
            keep_front_matter=args.keep_front_matter,
        )
    except ValueError as exc:
        print_json(
            build_command_response(
                "replace-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["list_document_blocks"],
                    OFFICIAL_REFERENCES["delete_block_children"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                error=str(exc),
            )
        )
        return 1
    except FileNotFoundError as exc:
        print_json(
            build_command_response(
                "replace-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["list_document_blocks"],
                    OFFICIAL_REFERENCES["delete_block_children"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "replace-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["list_document_blocks"],
                    OFFICIAL_REFERENCES["delete_block_children"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "replace-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["list_document_blocks"],
                    OFFICIAL_REFERENCES["delete_block_children"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                request={
                    "document_id": args.document_id,
                    "document_revision_id": args.document_revision_id,
                    "user_id_type": args.user_id_type,
                    "confirm_replace": bool(args.confirm_replace),
                    "keep_front_matter": bool(args.keep_front_matter),
                    "show_converted_blocks": bool(args.show_converted_blocks),
                },
                auth=auth,
                error="Failed to resolve tenant_access_token for replace-markdown.",
            )
        )
        return 1

    if not args.confirm_replace:
        print_json(
            build_command_response(
                "replace-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["list_document_blocks"],
                    OFFICIAL_REFERENCES["delete_block_children"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                request={
                    "document_id": args.document_id,
                    "confirm_replace": False,
                },
                auth=auth,
                error="replace-markdown is destructive. Re-run with --confirm-replace to clear the remote doc body first.",
            )
        )
        return 1

    if not markdown_content.strip():
        print_json(
            build_command_response(
                "replace-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["list_document_blocks"],
                    OFFICIAL_REFERENCES["delete_block_children"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                request={
                    "document_id": args.document_id,
                    "confirm_replace": True,
                    "keep_front_matter": bool(args.keep_front_matter),
                },
                auth=auth,
                error="Markdown input is empty after preprocessing.",
            )
        )
        return 1

    response = replace_markdown_in_document(
        tenant_access_token=str(token_result["tenant_access_token"]),
        document_id=args.document_id,
        markdown_content=markdown_content,
        source_info=source_info,
        base_url=base_url,
        timeout=args.timeout,
        document_revision_id=args.document_revision_id,
        user_id_type=args.user_id_type,
        show_converted_blocks=args.show_converted_blocks,
    )
    response["token_source"] = token_result.get("source")
    result_payload = dict(response)
    notes = result_payload.pop("notes", [])
    print_json(
        build_command_response(
            "replace-markdown",
            response["ok"],
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[
                TOKEN_DOCS["tenant_access_token_internal"],
                OFFICIAL_REFERENCES["list_document_blocks"],
                OFFICIAL_REFERENCES["delete_block_children"],
                OFFICIAL_REFERENCES["convert_markdown_html"],
                OFFICIAL_REFERENCES["create_descendant_blocks"],
            ],
            request={
                "document_id": args.document_id,
                "document_revision_id": args.document_revision_id,
                "user_id_type": args.user_id_type,
                "confirm_replace": bool(args.confirm_replace),
                "keep_front_matter": bool(args.keep_front_matter),
                "show_converted_blocks": bool(args.show_converted_blocks),
                "markdown_source": source_info,
            },
            auth=auth,
            result=result_payload,
            error=None if response["ok"] else "Failed to replace the Feishu document body with converted Markdown.",
            notes=notes,
        )
    )
    return 0 if response["ok"] else 1


def command_push_markdown(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "push-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["create_document"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "push-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["create_document"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "push-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["create_document"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                request={
                    "path": str(Path(args.path).resolve()),
                    "root": str(Path(args.root).resolve()) if args.root else None,
                    "index_path": args.index_path,
                    "folder_token": args.folder_token,
                    "keep_front_matter": bool(args.keep_front_matter),
                    "confirm_replace": bool(args.confirm_replace),
                    "ignore_sync_direction": bool(args.ignore_sync_direction),
                },
                auth=auth,
                error="Failed to resolve tenant_access_token for push-markdown.",
            )
        )
        return 1

    try:
        result = execute_push_markdown(
            markdown_path=Path(args.path),
            tenant_access_token=str(token_result["tenant_access_token"]),
            base_url=normalize_base_url(args.base_url),
            timeout=args.timeout,
            root=Path(args.root).resolve() if args.root else None,
            index_path=args.index_path,
            folder_token_override=args.folder_token,
            keep_front_matter=args.keep_front_matter,
            confirm_replace=args.confirm_replace,
            ignore_sync_direction=args.ignore_sync_direction,
        )
    except (ValueError, FileNotFoundError) as exc:
        print_json(
            build_command_response(
                "push-markdown",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["create_document"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                request={
                    "path": str(Path(args.path).resolve()),
                    "root": str(Path(args.root).resolve()) if args.root else None,
                    "index_path": args.index_path,
                    "folder_token": args.folder_token,
                    "keep_front_matter": bool(args.keep_front_matter),
                    "confirm_replace": bool(args.confirm_replace),
                    "ignore_sync_direction": bool(args.ignore_sync_direction),
                },
                auth=auth,
                error=str(exc),
            )
        )
        return 1

    result_payload = dict(result)
    notes = result_payload.pop("notes", [])
    print_json(
        build_command_response(
            "push-markdown",
            result.get("ok", False),
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=[
                TOKEN_DOCS["tenant_access_token_internal"],
                OFFICIAL_REFERENCES["create_document"],
                OFFICIAL_REFERENCES["convert_markdown_html"],
                OFFICIAL_REFERENCES["create_descendant_blocks"],
            ],
            request={
                "path": str(Path(args.path).resolve()),
                "root": str(Path(args.root).resolve()) if args.root else None,
                "index_path": args.index_path,
                "folder_token": args.folder_token,
                "keep_front_matter": bool(args.keep_front_matter),
                "confirm_replace": bool(args.confirm_replace),
                "ignore_sync_direction": bool(args.ignore_sync_direction),
            },
            auth=auth,
            result=result_payload,
            error=None if result.get("ok") else "push-markdown did not finish successfully.",
            notes=notes,
        )
    )
    return 0 if result.get("ok") else 1


def command_push_dir(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    official_docs = [
        TOKEN_DOCS["tenant_access_token_internal"],
        OFFICIAL_REFERENCES["create_document"],
        OFFICIAL_REFERENCES["convert_markdown_html"],
        OFFICIAL_REFERENCES["create_descendant_blocks"],
    ]
    if args.mirror_remote_folders:
        official_docs = normalize_reference_list(
            official_docs,
            [
                OFFICIAL_REFERENCES["create_folder"],
                OFFICIAL_REFERENCES["root_folder_meta"],
                OFFICIAL_REFERENCES["list_drive_files"],
            ],
        )
    request_payload = {
        "path": str(Path(args.path).resolve()),
        "index_path": args.index_path,
        "folder_token": args.folder_token,
        "keep_front_matter": bool(args.keep_front_matter),
        "confirm_replace": bool(args.confirm_replace),
        "ignore_sync_direction": bool(args.ignore_sync_direction),
        "continue_on_error": bool(args.continue_on_error),
        "mirror_remote_folders": bool(args.mirror_remote_folders),
    }
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "push-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "push-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "push-dir",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=request_payload,
                auth=auth,
                error="Failed to resolve tenant_access_token for push-dir.",
            )
        )
        return 1

    root = Path(args.path).resolve()
    if not root.is_dir():
        print_json(
            build_command_response(
                "push-dir",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=dict(request_payload, path=str(root)),
                auth=auth,
                error=f"Markdown directory not found: {root}",
            )
        )
        return 1

    effective_index_path = resolve_index_path(root, args.index_path)
    folder_cache: Optional[Dict[str, str]] = None
    child_listing_cache: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None
    root_folder_token: Optional[str] = None
    if args.mirror_remote_folders:
        index_entries = load_index(effective_index_path)
        directory_folder_tokens, directory_conflicts = build_directory_folder_token_index(index_entries)
        if directory_conflicts:
            print_json(
                build_command_response(
                    "push-dir",
                    False,
                    mode="tenant",
                    base_url=base_url,
                    token_source=token_result.get("source"),
                    official_docs=official_docs,
                    request=dict(request_payload, path=str(root)),
                    auth=auth,
                    result={"directory_folder_conflicts": directory_conflicts},
                    error="Conflicting folder_token mappings were found for one or more local directories. Resolve feishu-index.json before using --mirror-remote-folders.",
                )
            )
            return 1

        folder_ref = resolve_drive_folder_reference(
            tenant_access_token=str(token_result["tenant_access_token"]),
            base_url=base_url,
            timeout=args.timeout,
            folder_token=args.folder_token,
        )
        if not folder_ref["ok"] or not folder_ref.get("token"):
            print_json(
                build_command_response(
                    "push-dir",
                    False,
                    mode="tenant",
                    base_url=base_url,
                    token_source=token_result.get("source"),
                    official_docs=official_docs,
                    request=dict(request_payload, path=str(root)),
                    auth=auth,
                    result={"folder": folder_ref},
                    error="Failed to resolve the remote root folder for push-dir folder mirroring.",
                )
            )
            return 1

        root_folder_token = str(folder_ref["token"])
        folder_cache = {"": root_folder_token}
        for relative_dir, folder_token in directory_folder_tokens.items():
            normalized_relative_dir = normalize_relative_dir(relative_dir)
            if normalized_relative_dir:
                folder_cache.setdefault(normalized_relative_dir, folder_token)
        child_listing_cache = {}

    files = iter_markdown_files(root)
    results: List[Dict[str, Any]] = []
    pushed = 0
    skipped = 0
    failed = 0

    for path in files:
        derived_folder_token = None
        folder_resolution = None
        try:
            if args.mirror_remote_folders and root_folder_token and folder_cache is not None and child_listing_cache is not None:
                plan = plan_file(path, mode="push", root=root, index_path=effective_index_path)
                if plan.get("action") == "create_doc_in_root":
                    relative_dir = normalize_relative_dir(Path(str(plan["relative_path"])).parent.as_posix())
                    folder_resolution = ensure_remote_folder_hierarchy(
                        tenant_access_token=str(token_result["tenant_access_token"]),
                        root_folder_token=root_folder_token,
                        relative_dir=relative_dir,
                        base_url=base_url,
                        timeout=args.timeout,
                        folder_cache=folder_cache,
                        child_listing_cache=child_listing_cache,
                    )
                    if not folder_resolution["ok"]:
                        result = {
                            "ok": False,
                            "path": str(path.resolve()),
                            "relative_path": str(plan["relative_path"]),
                            "title": plan.get("title"),
                            "action": "resolve_remote_folder_hierarchy",
                            "folder_resolution": folder_resolution,
                            "error": folder_resolution.get(
                                "error",
                                "Failed to resolve the remote folder hierarchy for the local directory mirror.",
                            ),
                        }
                        results.append(result)
                        failed += 1
                        if not args.continue_on_error:
                            break
                        continue
                    derived_folder_token = str(folder_resolution.get("folder_token") or "")

            result = execute_push_markdown(
                markdown_path=path,
                tenant_access_token=str(token_result["tenant_access_token"]),
                base_url=base_url,
                timeout=args.timeout,
                root=root,
                index_path=args.index_path,
                folder_token_override=None if args.mirror_remote_folders else args.folder_token,
                folder_token_fallback=derived_folder_token,
                keep_front_matter=args.keep_front_matter,
                confirm_replace=args.confirm_replace,
                ignore_sync_direction=args.ignore_sync_direction,
                folder_resolution=folder_resolution,
            )
        except (ValueError, FileNotFoundError) as exc:
            result = {
                "ok": False,
                "path": str(path.resolve()),
                "relative_path": path.resolve().relative_to(root).as_posix(),
                "error": str(exc),
            }
        results.append(result)
        if result.get("ok") and not result.get("skipped"):
            pushed += 1
            continue
        if result.get("skipped"):
            skipped += 1
            continue
        failed += 1
        if not args.continue_on_error:
            break

    result_payload = {
        "root": str(root),
        "index_path": str(effective_index_path),
        "file_count": len(files),
        "pushed_count": pushed,
        "skipped_count": skipped,
        "failed_count": failed,
        "mirror_remote_folders": bool(args.mirror_remote_folders),
        "results": results,
    }
    notes = [
            "push-dir executes tenant-mode push-markdown for every Markdown file under the target root.",
            "Existing documents require --confirm-replace because updates clear the remote doc body before writing.",
    ]
    if args.mirror_remote_folders:
        notes.append(
            "With --mirror-remote-folders, new docs without an explicit folder token inherit a remote folder path derived from the local directory tree."
        )
    print_json(
        build_command_response(
            "push-dir",
            failed == 0,
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=official_docs,
            request=dict(request_payload, path=str(root)),
            auth=auth,
            result=result_payload,
            error=None if failed == 0 else "push-dir completed with one or more failed files.",
            notes=notes,
        )
    )
    return 0 if failed == 0 else 1


def command_pull_dir(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    official_docs = [
        TOKEN_DOCS["tenant_access_token_internal"],
        OFFICIAL_REFERENCES["root_folder_meta"],
        OFFICIAL_REFERENCES["list_drive_files"],
        OFFICIAL_REFERENCES["get_document"],
        OFFICIAL_REFERENCES["get_raw_content"],
    ]
    if args.fidelity == "high":
        official_docs = normalize_reference_list(official_docs, [OFFICIAL_REFERENCES["list_document_blocks"]])
    request_payload = {
        "path": args.path,
        "folder_token": args.folder_token,
        "recursive": bool(args.recursive),
        "overwrite": bool(args.overwrite),
        "continue_on_error": bool(args.continue_on_error),
        "sync_direction": args.sync_direction,
        "index_path": args.index_path,
        "fidelity": args.fidelity,
    }
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "pull-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "pull-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "pull-dir",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=request_payload,
                auth=auth,
                error="Failed to resolve tenant_access_token for pull-dir.",
            )
        )
        return 1

    root = Path(args.path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    existing_markdown_paths = {path.relative_to(root).as_posix() for path in iter_markdown_files(root)}
    index_entries = load_index(resolve_index_path(root, args.index_path))
    doc_token_index = build_doc_token_index(index_entries)
    used_paths = set(existing_markdown_paths)

    listing = list_drive_folder_contents(
        tenant_access_token=str(token_result["tenant_access_token"]),
        base_url=base_url,
        timeout=args.timeout,
        folder_token=args.folder_token,
        recursive=args.recursive,
        max_depth=args.max_depth,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )
    if not listing["ok"]:
        print_json(
            build_command_response(
                "pull-dir",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=dict(request_payload, path=str(root)),
                auth=auth,
                result={"remote_listing": listing},
                error=listing.get("error", "Failed to enumerate the remote folder tree for pull-dir."),
            )
        )
        return 1

    remote_docs = [item for item in listing["items"] if is_drive_docx_type(item.get("type"))]
    results: List[Dict[str, Any]] = []
    pulled = 0
    failed = 0

    for remote_doc in remote_docs:
        doc_token = str(remote_doc.get("token") or "")
        if not doc_token:
            continue
        relative_path, path_source = derive_relative_pull_path(remote_doc, doc_token_index, used_paths)
        result = execute_pull_markdown(
            document_id=doc_token,
            tenant_access_token=str(token_result["tenant_access_token"]),
            base_url=base_url,
            timeout=args.timeout,
            root=root,
            index_path=args.index_path,
            overwrite=args.overwrite,
            sync_direction=args.sync_direction,
            title_override=str(remote_doc.get("name") or ""),
            folder_token=args.folder_token or str(remote_doc.get("folder_token") or ""),
            relative_path_hint=relative_path,
            write_index=True,
            fidelity=args.fidelity,
        )
        result["path_source"] = path_source
        results.append(result)
        if result.get("ok"):
            pulled += 1
            continue
        failed += 1
        if not args.continue_on_error:
            break

    response_ok = failed == 0
    print_json(
        build_command_response(
            "pull-dir",
            response_ok,
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=official_docs,
            request=dict(request_payload, path=str(root)),
            auth=auth,
            result={
                "root": str(root),
                "index_path": str(resolve_index_path(root, args.index_path)),
                "remote_listing": {
                    "page_count": listing["page_count"],
                    "folder_count": listing["folder_count"],
                    "file_count": listing["file_count"],
                    "item_count": listing["item_count"],
                },
                "remote_doc_count": len(remote_docs),
                "pulled_count": pulled,
                "failed_count": failed,
                "fidelity": args.fidelity,
                "results": results,
            },
            error=None if response_ok else "pull-dir completed with one or more failed documents.",
            notes=(
                [
                    "pull-dir used the Feishu block tree to rebuild higher-fidelity Markdown for common block types."
                ]
                if args.fidelity == "high"
                else [
                    "pull-dir currently exports low-fidelity Markdown based on the Feishu raw_content API."
                ]
            )
            + [
                "The command writes feishu-index.json entries so later push and pull planning can reuse the same mappings.",
            ],
        )
    )
    return 0 if response_ok else 1


def command_sync_dir(args: argparse.Namespace) -> int:
    base_url = normalize_base_url(args.base_url)
    official_docs = [
        TOKEN_DOCS["tenant_access_token_internal"],
        OFFICIAL_REFERENCES["root_folder_meta"],
        OFFICIAL_REFERENCES["list_drive_files"],
        OFFICIAL_REFERENCES["get_document"],
        OFFICIAL_REFERENCES["get_raw_content"],
    ]
    if args.prune:
        official_docs = normalize_reference_list(official_docs, [OFFICIAL_REFERENCES["delete_file"]])
    if args.include_diff and args.diff_fidelity == "high":
        official_docs = normalize_reference_list(official_docs, [OFFICIAL_REFERENCES["list_document_blocks"]])
    if args.execute_bidirectional:
        official_docs = normalize_reference_list(
            official_docs,
            [
                OFFICIAL_REFERENCES["list_document_blocks"],
                OFFICIAL_REFERENCES["convert_markdown_html"],
                OFFICIAL_REFERENCES["create_descendant_blocks"],
                OFFICIAL_REFERENCES["delete_block_children"],
            ],
        )
    request_payload = {
        "path": args.path,
        "folder_token": args.folder_token,
        "index_path": args.index_path,
        "recursive": bool(args.recursive),
        "max_depth": args.max_depth,
        "page_size": args.page_size,
        "max_pages": args.max_pages,
        "dry_run": bool(args.dry_run),
        "prune": bool(args.prune),
        "confirm_prune": bool(args.confirm_prune),
        "execute_bidirectional": bool(args.execute_bidirectional),
        "confirm_bidirectional": bool(args.confirm_bidirectional),
        "pull_fidelity": args.pull_fidelity,
        "detect_conflicts": bool(args.detect_conflicts),
        "include_diff": bool(args.include_diff),
        "diff_fidelity": args.diff_fidelity,
        "diff_max_lines": args.diff_max_lines,
        "backup_dir": args.backup_dir,
        "continue_on_error": bool(args.continue_on_error),
        "allow_auto_merge": bool(args.allow_auto_merge),
        "adopt_remote_new": bool(args.adopt_remote_new),
        "include_create_flow": bool(args.include_create_flow),
    }
    if args.prune and args.execute_bidirectional:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="Choose either --prune or --execute-bidirectional for sync-dir execution, not both in the same run.",
            )
        )
        return 1
    if not args.dry_run and not args.prune and not args.execute_bidirectional:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="sync-dir execution currently supports either --prune --confirm-prune or --execute-bidirectional --confirm-bidirectional. Re-run with --dry-run for planning when you are not ready to execute.",
            )
        )
        return 1
    if args.dry_run and args.execute_bidirectional:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="Use either --dry-run for planning or --execute-bidirectional for execution, not both in the same run.",
            )
        )
        return 1
    if args.include_diff and not args.detect_conflicts:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="Diff preview requires --detect-conflicts so sync-dir can inspect local vs remote drift before execution.",
            )
        )
        return 1
    if args.include_diff and not args.dry_run:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="Diff preview is available only during --dry-run planning.",
            )
        )
        return 1
    if not args.dry_run and args.detect_conflicts and not args.execute_bidirectional:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="Conflict detection currently runs only with --dry-run. Re-run with --dry-run --detect-conflicts before any execution step.",
            )
        )
        return 1
    if args.diff_max_lines <= 0:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="--diff-max-lines must be a positive integer.",
            )
        )
        return 1
    if args.confirm_bidirectional and not args.execute_bidirectional:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="--confirm-bidirectional only applies when --execute-bidirectional is enabled.",
            )
        )
        return 1
    if (args.allow_auto_merge or args.adopt_remote_new or args.include_create_flow) and not args.execute_bidirectional:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="--allow-auto-merge, --adopt-remote-new, and --include-create-flow only apply when --execute-bidirectional is enabled.",
            )
        )
        return 1
    if not args.dry_run and args.execute_bidirectional and not args.confirm_bidirectional:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="Protected bidirectional execution is destructive on both local and remote state. Re-run with --confirm-bidirectional after reviewing the dry-run plan.",
            )
        )
        return 1
    if args.pull_fidelity not in {"low", "high"}:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="--pull-fidelity must be either low or high.",
            )
        )
        return 1
    if not args.dry_run and args.prune and not args.confirm_prune:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                request=request_payload,
                error="Prune execution is destructive. Re-run with --confirm-prune after reviewing the dry-run plan and backup location.",
            )
        )
        return 1

    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1
    except RuntimeError as exc:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                official_docs=official_docs,
                error=str(exc),
            )
        )
        return 1

    auth = summarize_tenant_auth(token_result)
    if not token_result.get("ok"):
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=request_payload,
                auth=auth,
                error="Failed to resolve tenant_access_token for sync-dir.",
            )
        )
        return 1

    try:
        if args.dry_run:
            result = build_sync_dir_dry_run(
                root=Path(args.path),
                tenant_access_token=str(token_result["tenant_access_token"]),
                base_url=base_url,
                timeout=args.timeout,
                folder_token=args.folder_token,
                index_path=args.index_path,
                recursive=args.recursive,
                max_depth=args.max_depth,
                page_size=args.page_size,
                max_pages=args.max_pages,
                prune=args.prune,
                detect_conflicts=args.detect_conflicts,
                include_diff=args.include_diff,
                diff_fidelity=args.diff_fidelity,
                diff_max_lines=args.diff_max_lines,
            )
        elif args.execute_bidirectional:
            result = execute_sync_dir_bidirectional(
                root=Path(args.path),
                tenant_access_token=str(token_result["tenant_access_token"]),
                base_url=base_url,
                timeout=args.timeout,
                folder_token=args.folder_token,
                index_path=args.index_path,
                recursive=args.recursive,
                max_depth=args.max_depth,
                page_size=args.page_size,
                max_pages=args.max_pages,
                backup_dir=args.backup_dir,
                continue_on_error=args.continue_on_error,
                pull_fidelity=args.pull_fidelity,
                allow_auto_merge=args.allow_auto_merge,
                adopt_remote_new=args.adopt_remote_new,
                include_create_flow=args.include_create_flow,
            )
        else:
            result = execute_sync_dir_prune(
                root=Path(args.path),
                tenant_access_token=str(token_result["tenant_access_token"]),
                base_url=base_url,
                timeout=args.timeout,
                folder_token=args.folder_token,
                index_path=args.index_path,
                recursive=args.recursive,
                max_depth=args.max_depth,
                page_size=args.page_size,
                max_pages=args.max_pages,
                backup_dir=args.backup_dir,
                continue_on_error=args.continue_on_error,
            )
    except (ValueError, FileNotFoundError) as exc:
        print_json(
            build_command_response(
                "sync-dir",
                False,
                mode="tenant",
                base_url=base_url,
                token_source=token_result.get("source"),
                official_docs=official_docs,
                request=request_payload,
                auth=auth,
                error=str(exc),
            )
        )
        return 1

    result_payload = dict(result)
    notes = result_payload.pop("notes", [])
    print_json(
        build_command_response(
            "sync-dir",
            result.get("ok", False),
            mode="tenant",
            base_url=base_url,
            token_source=token_result.get("source"),
            official_docs=official_docs,
            request=request_payload,
            auth=auth,
            result=result_payload,
            error=None
            if result.get("ok")
            else result.get(
                "error",
                "Failed to execute sync-dir." if not args.dry_run else "Failed to build the sync-dir dry-run plan.",
            ),
            notes=notes,
        )
    )
    return 0 if result.get("ok") else 1


def command_plan_push(args: argparse.Namespace) -> int:
    plan = plan_file(Path(args.path), mode="push", root=Path(args.root).resolve() if args.root else None)
    print_json(
        build_command_response(
            "plan-push",
            True,
            mode="planning",
            request={
                "path": str(Path(args.path).resolve()),
                "root": str(Path(args.root).resolve()) if args.root else None,
            },
            result=plan,
        )
    )
    return 0


def command_plan_pull(args: argparse.Namespace) -> int:
    plan = plan_file(Path(args.path), mode="pull", root=Path(args.root).resolve() if args.root else None)
    print_json(
        build_command_response(
            "plan-pull",
            True,
            mode="planning",
            request={
                "path": str(Path(args.path).resolve()),
                "root": str(Path(args.root).resolve()) if args.root else None,
            },
            result=plan,
        )
    )
    return 0


def command_plan_dir(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    index_path = discover_index_path(root)
    plans = [plan_file(path, mode=args.mode, root=root, index_path=index_path) for path in iter_markdown_files(root)]

    summary = {
        "mode": args.mode,
        "root": str(root),
        "index_path": str(index_path.resolve()) if index_path else None,
        "file_count": len(plans),
        "actions": {},
        "plans": plans,
    }

    for plan in plans:
        action = str(plan["action"])
        summary["actions"][action] = summary["actions"].get(action, 0) + 1

    print_json(
        build_command_response(
            "plan-dir",
            True,
            mode="planning",
            request={
                "path": str(root),
                "mode": args.mode,
            },
            result=summary,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Feishu Markdown sync CLI for auth validation, live tenant writes, and planning."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Check local prerequisites and recommended scopes.")
    doctor_parser.set_defaults(func=command_doctor)

    scopes_parser = subparsers.add_parser("scopes", help="Print the recommended Feishu scopes for this scaffold.")
    scopes_parser.set_defaults(func=command_scopes)

    tenant_token_parser = subparsers.add_parser(
        "tenant-token",
        help="Obtain a tenant_access_token for a self-built Feishu app.",
    )
    tenant_token_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    tenant_token_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    tenant_token_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    tenant_token_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    tenant_token_parser.add_argument("--show-token", action="store_true", help="Include the full tenant_access_token in the JSON output.")
    tenant_token_parser.set_defaults(func=command_tenant_token)

    user_auth_url_parser = subparsers.add_parser(
        "user-auth-url",
        help="Build a Feishu browser authorization URL for a user login flow.",
    )
    user_auth_url_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    user_auth_url_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    user_auth_url_parser.add_argument("--redirect-uri", help="OAuth redirect URI. Defaults to FEISHU_REDIRECT_URI.")
    user_auth_url_parser.add_argument("--state", help="Optional caller-supplied state. Defaults to a generated random value.")
    user_auth_url_parser.add_argument("--scope", help="Optional raw scope string appended to the authorization URL.")
    user_auth_url_parser.set_defaults(func=command_user_auth_url)

    exchange_user_token_parser = subparsers.add_parser(
        "exchange-user-token",
        help="Exchange an OAuth authorization code for user_access_token credentials.",
    )
    exchange_user_token_parser.add_argument("code", help="Authorization code returned by the Feishu login redirect.")
    exchange_user_token_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    exchange_user_token_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    exchange_user_token_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    exchange_user_token_parser.add_argument("--redirect-uri", help="OAuth redirect URI. Defaults to FEISHU_REDIRECT_URI.")
    exchange_user_token_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    exchange_user_token_parser.add_argument("--show-tokens", action="store_true", help="Include full token values in the JSON output.")
    exchange_user_token_parser.set_defaults(func=command_exchange_user_token)

    authorize_local_parser = subparsers.add_parser(
        "authorize-local",
        help="Start a local callback server, open the Feishu auth page, and exchange the returned code automatically.",
    )
    authorize_local_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    authorize_local_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    authorize_local_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    authorize_local_parser.add_argument("--host", default="127.0.0.1", help="Local callback host. Defaults to 127.0.0.1.")
    authorize_local_parser.add_argument("--port", type=int, default=16666, help="Local callback port. Defaults to 16666.")
    authorize_local_parser.add_argument("--callback-path", default="/callback", help="Local callback path. Defaults to /callback.")
    authorize_local_parser.add_argument("--state", help="Optional caller-supplied state. Defaults to a generated random value.")
    authorize_local_parser.add_argument("--scope", help="Optional raw scope string appended to the authorization URL.")
    authorize_local_parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait for the local browser callback. Defaults to 300 to match Feishu's 5-minute code lifetime.")
    authorize_local_parser.add_argument("--request-timeout", type=int, default=20, help="HTTP timeout in seconds for Feishu API calls. Defaults to 20.")
    authorize_local_parser.add_argument("--no-open-browser", action="store_true", help="Do not open the browser automatically. The command will print the authorization URL instead.")
    authorize_local_parser.add_argument("--show-tokens", action="store_true", help="Include full token values in the JSON output.")
    authorize_local_parser.set_defaults(func=command_authorize_local)

    validate_tenant_parser = subparsers.add_parser(
        "validate-tenant",
        help="Fetch or reuse a tenant_access_token and validate connectivity.",
    )
    validate_tenant_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    validate_tenant_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    validate_tenant_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    validate_tenant_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    validate_tenant_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    validate_tenant_parser.add_argument("--document-id", help="Optional docx document id used for a read-only probe.")
    validate_tenant_parser.add_argument("--doc-token", help="Alias of --document-id for docx document token values.")
    validate_tenant_parser.set_defaults(func=command_validate_tenant)

    create_document_parser = subparsers.add_parser(
        "create-document",
        help="Create a real Feishu docx document with a tenant token.",
    )
    create_document_parser.add_argument("title", help="Document title.")
    create_document_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    create_document_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    create_document_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    create_document_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    create_document_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    create_document_parser.add_argument("--folder-token", help="Optional parent folder token for the new document.")
    create_document_parser.set_defaults(func=command_create_document)

    get_document_parser = subparsers.add_parser(
        "get-document",
        help="Fetch Feishu docx basic metadata for one document.",
    )
    get_document_parser.add_argument("document_id", help="Docx document id or token.")
    get_document_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    get_document_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    get_document_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    get_document_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    get_document_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    get_document_parser.set_defaults(func=command_get_document)

    get_raw_content_parser = subparsers.add_parser(
        "get-raw-content",
        help="Fetch Feishu docx plain-text content for one document with a tenant token.",
    )
    get_raw_content_parser.add_argument("document_id", help="Docx document id or token.")
    get_raw_content_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    get_raw_content_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    get_raw_content_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    get_raw_content_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    get_raw_content_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    get_raw_content_parser.set_defaults(func=command_get_raw_content)

    list_root_files_parser = subparsers.add_parser(
        "list-root-files",
        help="List files visible under the current Feishu drive root folder.",
    )
    list_root_files_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    list_root_files_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    list_root_files_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    list_root_files_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    list_root_files_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    list_root_files_parser.add_argument("--folder-token", help="Optional folder token override. Defaults to the resolved root folder token.")
    list_root_files_parser.add_argument("--page-size", type=int, default=100, help="Drive page size. Defaults to 100.")
    list_root_files_parser.add_argument("--one-page", action="store_true", help="Fetch only the first page.")
    list_root_files_parser.add_argument("--max-pages", type=int, default=20, help="Maximum pages to fetch when paging. Defaults to 20.")
    list_root_files_parser.set_defaults(func=command_list_root_files)

    list_folder_files_parser = subparsers.add_parser(
        "list-folder-files",
        help="List files under a specific Feishu folder token or the app-visible root folder.",
    )
    list_folder_files_parser.add_argument("--folder-token", help="Optional starting folder token. Defaults to the resolved root folder.")
    list_folder_files_parser.add_argument("--recursive", action="store_true", help="Walk nested folders recursively.")
    list_folder_files_parser.add_argument("--max-depth", type=int, default=20, help="Maximum recursion depth when --recursive is used. Defaults to 20.")
    list_folder_files_parser.add_argument("--page-size", type=int, default=100, help="Drive page size. Defaults to 100.")
    list_folder_files_parser.add_argument("--max-pages", type=int, default=20, help="Maximum pages to fetch across the whole traversal. Defaults to 20.")
    list_folder_files_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    list_folder_files_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    list_folder_files_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    list_folder_files_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    list_folder_files_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    list_folder_files_parser.set_defaults(func=command_list_folder_files)

    delete_document_parser = subparsers.add_parser(
        "delete-document",
        help="Delete a Feishu cloud document or drive file with a tenant token.",
    )
    delete_document_parser.add_argument("document_id", help="Drive file token or docx document token.")
    delete_document_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    delete_document_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    delete_document_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    delete_document_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    delete_document_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    delete_document_parser.add_argument("--file-type", default="docx", help="Drive file type query value. Defaults to docx.")
    delete_document_parser.set_defaults(func=command_delete_document)

    pull_markdown_parser = subparsers.add_parser(
        "pull-markdown",
        help="Export one Feishu docx document to a local Markdown file with selectable fidelity.",
    )
    pull_markdown_parser.add_argument("document_id", help="Docx document id or token.")
    pull_markdown_parser.add_argument("--output", help="Optional output Markdown file path. If omitted, a title-derived file is created under --root or the current directory.")
    pull_markdown_parser.add_argument("--root", help="Optional sync root used for relative output paths and feishu-index.json.")
    pull_markdown_parser.add_argument("--relative-path", help="Optional relative Markdown path used when deriving the output under --root.")
    pull_markdown_parser.add_argument("--index-path", help="Optional feishu-index.json override path.")
    pull_markdown_parser.add_argument("--folder-token", help="Optional folder token stored back into feishu-index.json when index write-back is enabled.")
    pull_markdown_parser.add_argument("--title", help="Optional title override used for the local Markdown file and front matter.")
    pull_markdown_parser.add_argument("--overwrite", action="store_true", help="Overwrite the local Markdown file if it already exists.")
    pull_markdown_parser.add_argument("--write-index", action="store_true", help="Write or update feishu-index.json even when --root is not explicitly set.")
    pull_markdown_parser.add_argument("--fidelity", choices=("low", "high"), default="low", help="Export mode. low uses raw_content; high rebuilds Markdown from document blocks for common block types.")
    pull_markdown_parser.add_argument("--sync-direction", choices=tuple(sorted(VALID_SYNC_DIRECTIONS)), default="pull", help="sync_direction value written into front matter and index metadata. Defaults to pull.")
    pull_markdown_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    pull_markdown_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    pull_markdown_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    pull_markdown_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    pull_markdown_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    pull_markdown_parser.set_defaults(func=command_pull_markdown)

    upload_media_parser = subparsers.add_parser(
        "upload-media",
        help="Upload a local media file to Feishu and return the media file_token.",
    )
    upload_media_parser.add_argument("document_id", help="Target Feishu docx document id or token.")
    upload_media_parser.add_argument("path", help="Path to the local file to upload.")
    upload_media_parser.add_argument("--parent-type", default="docx_image", help="Feishu media parent_type. Defaults to docx_image.")
    upload_media_parser.add_argument("--file-name", help="Optional uploaded file name override. Defaults to the local file name.")
    upload_media_parser.add_argument("--extra-drive-route-token", help="Optional drive route token forwarded in the extra upload payload.")
    upload_media_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    upload_media_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    upload_media_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    upload_media_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    upload_media_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    upload_media_parser.set_defaults(func=command_upload_media)

    append_markdown_parser = subparsers.add_parser(
        "append-markdown",
        help="Convert Markdown and append it into a Feishu docx document with a tenant token.",
    )
    append_markdown_parser.add_argument("document_id", help="Target Feishu docx document id or token.")
    append_markdown_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    append_markdown_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    append_markdown_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    append_markdown_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    append_markdown_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    append_markdown_parser.add_argument("--markdown-file", help="Path to a local Markdown file to append.")
    append_markdown_parser.add_argument("--content", help="Inline Markdown content to append.")
    append_markdown_parser.add_argument("--keep-front-matter", action="store_true", help="Do not strip YAML front matter when reading --markdown-file.")
    append_markdown_parser.add_argument("--parent-block-id", help="Optional parent block id. Defaults to the document root block.")
    append_markdown_parser.add_argument("--document-revision-id", type=int, default=-1, help="Document revision to edit. Defaults to -1 for latest.")
    append_markdown_parser.add_argument("--index", type=int, help="Optional child insertion index. Defaults to the API default end position.")
    append_markdown_parser.add_argument("--user-id-type", help="Optional user_id_type query value for block conversion and write requests.")
    append_markdown_parser.add_argument("--client-token", help="Optional UUIDv4 idempotency token for descendant block creation.")
    append_markdown_parser.add_argument("--show-converted-blocks", action="store_true", help="Include converted block payloads in the JSON output.")
    append_markdown_parser.set_defaults(func=command_append_markdown)

    replace_markdown_parser = subparsers.add_parser(
        "replace-markdown",
        help="Replace a Feishu docx document body with Markdown using a tenant token.",
    )
    replace_markdown_parser.add_argument("document_id", help="Target Feishu docx document id or token.")
    replace_markdown_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    replace_markdown_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    replace_markdown_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    replace_markdown_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    replace_markdown_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    replace_markdown_parser.add_argument("--markdown-file", help="Path to a local Markdown file to replace the remote body with.")
    replace_markdown_parser.add_argument("--content", help="Inline Markdown content to replace the remote body with.")
    replace_markdown_parser.add_argument("--keep-front-matter", action="store_true", help="Do not strip YAML front matter when reading --markdown-file.")
    replace_markdown_parser.add_argument("--document-revision-id", type=int, default=-1, help="Document revision to edit. Defaults to -1 for latest.")
    replace_markdown_parser.add_argument("--user-id-type", help="Optional user_id_type query value for block conversion and write requests.")
    replace_markdown_parser.add_argument("--show-converted-blocks", action="store_true", help="Include converted block payloads in the JSON output.")
    replace_markdown_parser.add_argument("--confirm-replace", action="store_true", help="Required safety flag for destructive remote replacement.")
    replace_markdown_parser.set_defaults(func=command_replace_markdown)

    push_markdown_parser = subparsers.add_parser(
        "push-markdown",
        help="Push one local Markdown file to Feishu and write back feishu-index.json.",
    )
    push_markdown_parser.add_argument("path", help="Path to the Markdown file.")
    push_markdown_parser.add_argument("--root", help="Optional sync root used for relative paths and feishu-index.json.")
    push_markdown_parser.add_argument("--index-path", help="Optional feishu-index.json override path.")
    push_markdown_parser.add_argument("--folder-token", help="Optional folder token override used when creating new docs.")
    push_markdown_parser.add_argument("--keep-front-matter", action="store_true", help="Do not strip YAML front matter when reading the Markdown file.")
    push_markdown_parser.add_argument("--ignore-sync-direction", action="store_true", help="Push even if the file is currently marked pull-only.")
    push_markdown_parser.add_argument("--confirm-replace", action="store_true", help="Required safety flag when updating an existing remote document.")
    push_markdown_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    push_markdown_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    push_markdown_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    push_markdown_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    push_markdown_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    push_markdown_parser.set_defaults(func=command_push_markdown)

    push_dir_parser = subparsers.add_parser(
        "push-dir",
        help="Push a Markdown directory to Feishu and write back feishu-index.json.",
    )
    push_dir_parser.add_argument("path", help="Path to the Markdown directory.")
    push_dir_parser.add_argument("--index-path", help="Optional feishu-index.json override path.")
    push_dir_parser.add_argument("--folder-token", help="Optional folder token override used when creating new docs.")
    push_dir_parser.add_argument("--keep-front-matter", action="store_true", help="Do not strip YAML front matter when reading Markdown files.")
    push_dir_parser.add_argument("--ignore-sync-direction", action="store_true", help="Push even if a file is currently marked pull-only.")
    push_dir_parser.add_argument("--confirm-replace", action="store_true", help="Required safety flag when updating existing remote documents.")
    push_dir_parser.add_argument("--continue-on-error", action="store_true", help="Continue processing remaining files after a failure.")
    push_dir_parser.add_argument("--mirror-remote-folders", action="store_true", help="Mirror the local directory tree into remote Feishu folders when creating new docs without an explicit folder token.")
    push_dir_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    push_dir_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    push_dir_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    push_dir_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    push_dir_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    push_dir_parser.set_defaults(func=command_push_dir)

    pull_dir_parser = subparsers.add_parser(
        "pull-dir",
        help="Export every visible docx file under a Feishu folder tree into local Markdown files.",
    )
    pull_dir_parser.add_argument("path", help="Local output root directory.")
    pull_dir_parser.add_argument("--folder-token", help="Optional starting folder token. Defaults to the resolved app-visible root folder.")
    pull_dir_parser.add_argument("--index-path", help="Optional feishu-index.json override path.")
    pull_dir_parser.add_argument("--overwrite", action="store_true", help="Overwrite local Markdown files when they already exist.")
    pull_dir_parser.add_argument("--continue-on-error", action="store_true", help="Continue processing remaining remote docs after a failure.")
    pull_dir_parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="Only read the top-level folder instead of walking nested folders.")
    pull_dir_parser.add_argument("--max-depth", type=int, default=20, help="Maximum recursion depth when recursive traversal is enabled. Defaults to 20.")
    pull_dir_parser.add_argument("--page-size", type=int, default=100, help="Drive page size. Defaults to 100.")
    pull_dir_parser.add_argument("--max-pages", type=int, default=20, help="Maximum pages to fetch across the traversal. Defaults to 20.")
    pull_dir_parser.add_argument("--fidelity", choices=("low", "high"), default="low", help="Export mode. low uses raw_content; high rebuilds Markdown from document blocks for common block types.")
    pull_dir_parser.add_argument("--sync-direction", choices=tuple(sorted(VALID_SYNC_DIRECTIONS)), default="pull", help="sync_direction value written into pulled front matter and index metadata. Defaults to pull.")
    pull_dir_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    pull_dir_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    pull_dir_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    pull_dir_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    pull_dir_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    pull_dir_parser.set_defaults(func=command_pull_dir, recursive=True)

    sync_dir_parser = subparsers.add_parser(
        "sync-dir",
        help="Build a tenant-mode directory sync plan that combines local mappings with remote folder visibility.",
    )
    sync_dir_parser.add_argument("path", help="Local Markdown sync root.")
    sync_dir_parser.add_argument("--folder-token", help="Optional starting remote folder token. Defaults to the app-visible root folder.")
    sync_dir_parser.add_argument("--index-path", help="Optional feishu-index.json override path.")
    sync_dir_parser.add_argument("--dry-run", action="store_true", help="Build a plan without executing remote deletes or index cleanup.")
    sync_dir_parser.add_argument("--prune", action="store_true", help="Include prune candidates in planning; with --confirm-prune and no --dry-run, execute the prune candidates.")
    sync_dir_parser.add_argument("--confirm-prune", action="store_true", help="Required safety flag before sync-dir executes remote prune deletes and index cleanup.")
    sync_dir_parser.add_argument("--execute-bidirectional", action="store_true", help="Execute protected bidirectional sync for cleanly mapped bidirectional files after conflict detection says they are only local_ahead or remote_ahead.")
    sync_dir_parser.add_argument("--confirm-bidirectional", action="store_true", help="Required safety flag before sync-dir overwrites local Markdown files or remote Feishu docs during protected bidirectional execution.")
    sync_dir_parser.add_argument("--pull-fidelity", choices=("low", "high"), default="low", help="When --execute-bidirectional pulls remote changes into local Markdown, low uses raw_content and high rebuilds common block types from the block tree.")
    sync_dir_parser.add_argument("--allow-auto-merge", action="store_true", help="With --execute-bidirectional, allow sync-dir to auto-merge non-overlapping semantic changes for local_and_remote_changed files when a stored baseline snapshot is available.")
    sync_dir_parser.add_argument("--adopt-remote-new", action="store_true", help="With --execute-bidirectional, pull visible unmapped remote docs into the local sync root and register them as bidirectional mappings.")
    sync_dir_parser.add_argument("--include-create-flow", action="store_true", help="With --execute-bidirectional, allow unmapped local bidirectional files to create new remote Feishu docs and write back their mappings.")
    sync_dir_parser.add_argument("--detect-conflicts", action="store_true", help="During --dry-run, inspect mapped visible docs and classify local drift, remote drift, and review-required conflicts from the last recorded sync baseline.")
    sync_dir_parser.add_argument("--include-diff", action="store_true", help="With --dry-run --detect-conflicts, attach a semantic block diff preview plus a truncated line diff between the local Markdown body and a comparable remote export.")
    sync_dir_parser.add_argument("--diff-fidelity", choices=("low", "high"), default="low", help="Remote export mode used for conflict diff previews. low compares against raw_content; high rebuilds common block types from the block tree before diffing.")
    sync_dir_parser.add_argument("--diff-max-lines", type=int, default=80, help="Maximum preview lines to include per inspected file when --include-diff is enabled. Defaults to 80.")
    sync_dir_parser.add_argument("--backup-dir", help="Optional backup root. Defaults to <sync-root>/.feishu-sync-backups.")
    sync_dir_parser.add_argument("--continue-on-error", action="store_true", help="Continue processing later prune candidates after a backup or delete failure.")
    sync_dir_parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="Only inspect the top-level remote folder instead of walking nested folders.")
    sync_dir_parser.add_argument("--max-depth", type=int, default=20, help="Maximum recursion depth when recursive traversal is enabled. Defaults to 20.")
    sync_dir_parser.add_argument("--page-size", type=int, default=100, help="Drive page size. Defaults to 100.")
    sync_dir_parser.add_argument("--max-pages", type=int, default=20, help="Maximum pages to fetch across the traversal. Defaults to 20.")
    sync_dir_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    sync_dir_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    sync_dir_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    sync_dir_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    sync_dir_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    sync_dir_parser.set_defaults(func=command_sync_dir, recursive=True)

    push_parser = subparsers.add_parser("plan-push", help="Plan a push for one Markdown file.")
    push_parser.add_argument("path", help="Path to the Markdown file.")
    push_parser.add_argument("--root", help="Optional sync root used for relative paths.")
    push_parser.set_defaults(func=command_plan_push)

    pull_parser = subparsers.add_parser("plan-pull", help="Plan a pull for one mapped Markdown file.")
    pull_parser.add_argument("path", help="Path to the Markdown file.")
    pull_parser.add_argument("--root", help="Optional sync root used for relative paths.")
    pull_parser.set_defaults(func=command_plan_pull)

    dir_parser = subparsers.add_parser("plan-dir", help="Plan a directory push or pull.")
    dir_parser.add_argument("path", help="Path to the Markdown directory.")
    dir_parser.add_argument(
        "--mode",
        choices=("push", "pull"),
        default="push",
        help="Plan direction. Defaults to push.",
    )
    dir_parser.set_defaults(func=command_plan_dir)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as exc:
        print_json(
            build_command_response(
                "cli",
                False,
                mode="local",
                error=str(exc),
            )
        )
        raise SystemExit(1)

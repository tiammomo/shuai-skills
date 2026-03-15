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
from datetime import datetime, timezone
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
import threading
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

INDEX_FILENAME = "feishu-index.json"
REQUIRED_ENV = ("FEISHU_APP_ID", "FEISHU_APP_SECRET")
OPTIONAL_TOKEN_ENV = (
    "FEISHU_APP_ACCESS_TOKEN",
    "FEISHU_TENANT_ACCESS_TOKEN",
    "FEISHU_USER_ACCESS_TOKEN",
)
OPTIONAL_ENV = ("FEISHU_BASE_URL", "FEISHU_REDIRECT_URI")
VALID_SYNC_DIRECTIONS = {"push", "pull", "bidirectional"}
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv"}

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
DELETE_DRIVE_FILE_ENDPOINT_TEMPLATE = "/open-apis/drive/v1/files/{file_token}"
CREATE_DESCENDANT_BLOCKS_ENDPOINT_TEMPLATE = "/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/descendant"
DELETE_BLOCK_CHILDREN_ENDPOINT_TEMPLATE = (
    "/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children/batch_delete"
)


def print_json(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=False))


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


def current_timestamp_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    keep_front_matter: bool = False,
    confirm_replace: bool = False,
    ignore_sync_direction: bool = False,
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
    folder_token = folder_token_override or mapping.get("folder_token")
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

    index_entry = update_index_entry(
        effective_index_path,
        relative_path,
        {
            "doc_token": final_doc_token,
            "title": title,
            "content_hash": sha256_text(markdown_content),
            "last_sync_at": current_timestamp_utc(),
            "sync_direction": sync_direction,
            "folder_token": str(folder_token) if folder_token else None,
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
        "source": source_info,
        "mapping_source": mapping_source,
        "content_hash": sha256_text(markdown_content),
        "index_path": str(effective_index_path),
        "index_entry": index_entry,
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
    try:
        token_result = resolve_tenant_token(args)
    except ValueError as exc:
        print_json(
            build_command_response(
                "push-dir",
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
                "push-dir",
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
                "push-dir",
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
                    "index_path": args.index_path,
                    "folder_token": args.folder_token,
                    "keep_front_matter": bool(args.keep_front_matter),
                    "confirm_replace": bool(args.confirm_replace),
                    "ignore_sync_direction": bool(args.ignore_sync_direction),
                    "continue_on_error": bool(args.continue_on_error),
                },
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
                official_docs=[
                    TOKEN_DOCS["tenant_access_token_internal"],
                    OFFICIAL_REFERENCES["create_document"],
                    OFFICIAL_REFERENCES["convert_markdown_html"],
                    OFFICIAL_REFERENCES["create_descendant_blocks"],
                ],
                request={
                    "path": str(root),
                    "index_path": args.index_path,
                    "folder_token": args.folder_token,
                    "keep_front_matter": bool(args.keep_front_matter),
                    "confirm_replace": bool(args.confirm_replace),
                    "ignore_sync_direction": bool(args.ignore_sync_direction),
                    "continue_on_error": bool(args.continue_on_error),
                },
                auth=auth,
                error=f"Markdown directory not found: {root}",
            )
        )
        return 1

    files = iter_markdown_files(root)
    results: List[Dict[str, Any]] = []
    pushed = 0
    skipped = 0
    failed = 0

    for path in files:
        try:
            result = execute_push_markdown(
                markdown_path=path,
                tenant_access_token=str(token_result["tenant_access_token"]),
                base_url=base_url,
                timeout=args.timeout,
                root=root,
                index_path=args.index_path,
                folder_token_override=args.folder_token,
                keep_front_matter=args.keep_front_matter,
                confirm_replace=args.confirm_replace,
                ignore_sync_direction=args.ignore_sync_direction,
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
        "index_path": str(resolve_index_path(root, args.index_path)),
        "file_count": len(files),
        "pushed_count": pushed,
        "skipped_count": skipped,
        "failed_count": failed,
        "results": results,
    }
    notes = [
            "push-dir executes tenant-mode push-markdown for every Markdown file under the target root.",
            "Existing documents require --confirm-replace because updates clear the remote doc body before writing.",
    ]
    print_json(
        build_command_response(
            "push-dir",
            failed == 0,
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
                "path": str(root),
                "index_path": args.index_path,
                "folder_token": args.folder_token,
                "keep_front_matter": bool(args.keep_front_matter),
                "confirm_replace": bool(args.confirm_replace),
                "ignore_sync_direction": bool(args.ignore_sync_direction),
                "continue_on_error": bool(args.continue_on_error),
            },
            auth=auth,
            result=result_payload,
            error=None if failed == 0 else "push-dir completed with one or more failed files.",
            notes=notes,
        )
    )
    return 0 if failed == 0 else 1


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
    push_dir_parser.add_argument("--app-id", help="Feishu app id. Defaults to FEISHU_APP_ID.")
    push_dir_parser.add_argument("--app-secret", help="Feishu app secret. Defaults to FEISHU_APP_SECRET.")
    push_dir_parser.add_argument("--base-url", help="Feishu base URL. Defaults to FEISHU_BASE_URL or https://open.feishu.cn.")
    push_dir_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds. Defaults to 20.")
    push_dir_parser.add_argument("--force-refresh", action="store_true", help="Ignore FEISHU_TENANT_ACCESS_TOKEN and fetch a new token from app credentials.")
    push_dir_parser.set_defaults(func=command_push_dir)

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

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .client import YuqueClient, build_path, build_repo_path, fetch_all_pages, fetch_doc_detail, unwrap_data
from .core import DEFAULT_LIMIT, YuqueApiError, maybe_json

def should_reuse_doc_lookup_as_slug(doc_ref: str, lookup_by: str) -> bool:
    if lookup_by == "slug":
        return True
    if lookup_by == "id":
        return False
    return not doc_ref.isdigit()

def parse_front_matter_scalar(raw: str) -> Any:
    if raw == "":
        return ""
    if raw[0] in {'"', "[", "{"} or raw in {"null", "true", "false"} or re.fullmatch(
        r"-?\d+(?:\.\d+)?",
        raw,
    ):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw

def parse_front_matter_block(block: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in raw_line:
            continue
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        metadata[key] = parse_front_matter_scalar(raw_value.strip())
    return metadata

def split_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            block = "".join(lines[1:index])
            remainder = "".join(lines[index + 1 :])
            return parse_front_matter_block(block), remainder.lstrip("\r\n")
    return {}, text

def strip_front_matter(text: str) -> str:
    return split_front_matter(text)[1]

def derive_markdown_title(markdown: str, fallback: str) -> str:
    match = re.search(r"^\s*#\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return fallback

def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", name).strip().strip(".")
    return sanitized or "doc"

def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def front_matter_text(metadata: Dict[str, Any], key: str) -> Optional[str]:
    value = metadata.get(key)
    if value in (None, ""):
        return None
    return str(value)

def coerce_public_flag(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)) and int(value) in {0, 1}:
        return int(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"0", "1"}:
            return int(lowered)
        if lowered in {"true", "false"}:
            return 1 if lowered == "true" else 0
    return None

def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)

def build_doc_front_matter(doc: Dict[str, Any], repo_ref: str) -> str:
    lines = [
        "---",
        f"yuque_repo: {yaml_scalar(repo_ref)}",
        f"yuque_doc_id: {yaml_scalar(doc.get('id'))}",
        f"yuque_doc_slug: {yaml_scalar(doc.get('slug'))}",
        f"title: {yaml_scalar(doc.get('title'))}",
        f"public: {yaml_scalar(doc.get('public'))}",
        f"format: {yaml_scalar(doc.get('format'))}",
        f"updated_at: {yaml_scalar(doc.get('updated_at'))}",
        "---",
        "",
    ]
    return "\n".join(lines)

def doc_markdown_body(doc: Dict[str, Any]) -> str:
    body = doc.get("body")
    if isinstance(body, str):
        return body
    raise YuqueApiError("Doc payload did not include a markdown body.")

def current_utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def normalize_markdown_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")

def hash_markdown_content(text: str) -> str:
    return hashlib.sha256(normalize_markdown_text(text).encode("utf-8")).hexdigest()

def pull_doc_to_markdown(
    client: YuqueClient,
    *,
    repo_ref: str,
    doc_ref: str,
    output_path: Path,
    front_matter: bool,
) -> Dict[str, Any]:
    doc = fetch_doc_detail(client, repo_ref, doc_ref)
    ensure_parent_dir(output_path)
    body = doc_markdown_body(doc)
    content = build_doc_front_matter(doc, repo_ref) + body if front_matter else body
    output_path.write_text(content, encoding="utf-8")
    return {
        "repo": repo_ref,
        "doc_id": doc.get("id"),
        "doc_slug": doc.get("slug"),
        "title": doc.get("title"),
        "output": str(output_path),
        "bytes": len(content.encode("utf-8")),
    }

def export_repo_markdown_bundle(
    client: YuqueClient,
    *,
    repo_ref: str,
    export_dir: Path,
    front_matter: bool,
    index_file: str,
    name_by: str,
) -> Dict[str, Any]:
    export_dir.mkdir(parents=True, exist_ok=True)

    docs_response = fetch_all_pages(
        lambda offset, limit: client.request(
            "GET",
            build_repo_path(repo_ref) + build_path("docs"),
            query={"offset": offset, "limit": limit},
        ),
        offset=0,
        limit=DEFAULT_LIMIT,
    )
    docs = unwrap_data(docs_response)
    if not isinstance(docs, list):
        raise YuqueApiError("Expected doc list while exporting repo markdown.")

    exported = []
    for item in docs:
        if not isinstance(item, dict):
            continue
        doc_ref = str(item.get("id") or item.get("slug") or "")
        if not doc_ref:
            continue
        doc = fetch_doc_detail(client, repo_ref, doc_ref)

        if name_by == "title":
            base_name = str(doc.get("title") or doc.get("slug") or doc.get("id") or "doc")
        elif name_by == "id":
            base_name = str(doc.get("id") or doc.get("slug") or "doc")
        else:
            base_name = str(doc.get("slug") or doc.get("id") or doc.get("title") or "doc")

        filename = sanitize_filename(base_name) + ".md"
        output_path = export_dir / filename
        body = doc_markdown_body(doc)
        content = build_doc_front_matter(doc, repo_ref) + body if front_matter else body
        output_path.write_text(content, encoding="utf-8")

        exported.append(
            {
                "id": doc.get("id"),
                "slug": doc.get("slug"),
                "title": doc.get("title"),
                "path": str(output_path),
                "updated_at": doc.get("updated_at"),
                "public": doc.get("public"),
                "format": doc.get("format"),
            }
        )

    index_path = export_dir / index_file
    index_path.write_text(
        json.dumps(
            {
                "repo": repo_ref,
                "generated_at": current_utc_timestamp(),
                "count": len(exported),
                "docs": exported,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return {
        "repo": repo_ref,
        "output_dir": str(export_dir),
        "index_file": str(index_path),
        "count": len(exported),
        "docs": exported,
    }

def push_markdown_file(
    client: YuqueClient,
    *,
    repo_ref: str,
    source_path: Path,
    doc_ref: Optional[str],
    title: Optional[str],
    slug: Optional[str],
    public: Optional[int],
    lookup_by: str,
    keep_front_matter: bool,
    extra_json: Any,
) -> Dict[str, Any]:
    raw_markdown = source_path.read_text(encoding="utf-8")
    front_matter, stripped_markdown = split_front_matter(raw_markdown)
    body = raw_markdown if keep_front_matter else stripped_markdown
    file_stem = source_path.stem
    resolved_title = title or derive_markdown_title(
        stripped_markdown,
        front_matter_text(front_matter, "title") or file_stem,
    )

    lookup_doc = (
        doc_ref
        or front_matter_text(front_matter, "yuque_doc_id")
        or front_matter_text(front_matter, "yuque_doc_slug")
        or slug
        or file_stem
    )
    payload: Dict[str, Any] = {
        "title": resolved_title,
        "format": "markdown",
        "body": body,
    }
    public_value = public if public is not None else coerce_public_flag(front_matter.get("public"))
    if public_value is not None:
        payload["public"] = public_value
    slug_value = slug or front_matter_text(front_matter, "yuque_doc_slug")
    if slug_value:
        payload["slug"] = slug_value
    payload.update(maybe_json(extra_json, field_name="--extra-json"))

    path = build_repo_path(repo_ref) + build_path("docs", str(lookup_doc))
    action = "updated"
    try:
        client.request("GET", path)
    except YuqueApiError as exc:
        if exc.status != 404:
            raise
        action = "created"
        if "slug" not in payload:
            if slug:
                payload["slug"] = slug
            elif should_reuse_doc_lookup_as_slug(str(lookup_doc), lookup_by):
                payload["slug"] = lookup_doc
            else:
                payload["slug"] = file_stem
        response = client.request(
            "POST",
            build_repo_path(repo_ref) + build_path("docs"),
            payload=payload,
        )
        doc = unwrap_data(response)
        return {
            "action": action,
            "repo": repo_ref,
            "source": str(source_path),
            "doc_id": doc.get("id") if isinstance(doc, dict) else None,
            "doc_slug": doc.get("slug") if isinstance(doc, dict) else payload.get("slug"),
            "title": doc.get("title") if isinstance(doc, dict) else payload["title"],
        }

    response = client.request("PUT", path, payload=payload)
    doc = unwrap_data(response)
    return {
        "action": action,
        "repo": repo_ref,
        "source": str(source_path),
        "doc_id": doc.get("id") if isinstance(doc, dict) else None,
        "doc_slug": doc.get("slug") if isinstance(doc, dict) else lookup_doc,
        "title": doc.get("title") if isinstance(doc, dict) else payload["title"],
    }

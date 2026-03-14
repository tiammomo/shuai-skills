from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set

from .dir_sync_types import RecordLike, RecordMaps
from .markdown_docs import sanitize_filename


def relative_markdown_stem(relative_path: Path) -> Path:
    stem_path = relative_path.with_suffix("")
    if stem_path.name == "index" and stem_path.parent != Path("."):
        return stem_path.parent
    return stem_path


def slugify_for_yuque(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")


def reserve_unique_slug(candidate: str, used: Set[str], seed: str) -> str:
    base = candidate or "doc"
    proposed = base
    if proposed and proposed not in used:
        used.add(proposed)
        return proposed

    suffix = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    proposed = f"{base}-{suffix}"
    if proposed not in used:
        used.add(proposed)
        return proposed

    counter = 2
    while True:
        alt = f"{proposed}-{counter}"
        if alt not in used:
            used.add(alt)
            return alt
        counter += 1


def derive_dir_sync_slug(relative_path: Path, slug_source: str, used: Set[str]) -> str:
    source = relative_path.stem if slug_source == "stem" else relative_markdown_stem(relative_path).as_posix()
    candidate = slugify_for_yuque(source)
    return reserve_unique_slug(candidate, used, relative_path.as_posix())


def doc_name_value(source: Mapping[str, Any], name_by: str) -> str:
    if name_by == "title":
        value = source.get("title") or source.get("slug") or source.get("doc_id") or source.get("id")
    elif name_by == "id":
        value = source.get("doc_id") or source.get("id") or source.get("slug") or source.get("title")
    else:
        value = source.get("slug") or source.get("title") or source.get("doc_id") or source.get("id")
    return sanitize_filename(str(value or "doc"))


def flat_relative_markdown_path(source: Mapping[str, Any], name_by: str) -> str:
    return f"{doc_name_value(source, name_by)}.md"


def normalize_relative_path(path_value: Any, root_dir: Path) -> Optional[str]:
    if path_value in (None, ""):
        return None
    path = Path(str(path_value))
    if path.is_absolute():
        try:
            path = path.relative_to(root_dir)
        except ValueError:
            return None
    return path.as_posix()


def find_record(mapping: Mapping[str, RecordLike], *candidates: Any) -> Optional[RecordLike]:
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        record = mapping.get(str(candidate))
        if record is not None:
            return record
    return None


def build_toc_path_map(toc_items: List[Dict[str, Any]], name_by: str) -> Dict[str, str]:
    items_by_uuid = {
        str(item.get("uuid")): item
        for item in toc_items
        if item.get("uuid") not in (None, "")
    }
    children_by_parent: Dict[str, List[Dict[str, Any]]] = {}
    for item in toc_items:
        parent_uuid = str(item.get("parent_uuid") or "")
        children_by_parent.setdefault(parent_uuid, []).append(item)

    memo: Dict[str, List[str]] = {}

    def components_for(uuid_value: str) -> List[str]:
        if uuid_value in memo:
            return memo[uuid_value]
        item = items_by_uuid.get(uuid_value)
        if item is None:
            return []
        parent_uuid = str(item.get("parent_uuid") or "")
        components = list(components_for(parent_uuid))
        components.append(doc_name_value(item, name_by))
        memo[uuid_value] = components
        return components

    path_map: Dict[str, str] = {}
    for item in toc_items:
        uuid_value = str(item.get("uuid") or "")
        if not uuid_value:
            continue
        components = components_for(uuid_value)
        if not components:
            continue
        relative_path = Path(*components) / "index.md" if children_by_parent.get(uuid_value) else Path(*components[:-1]) / f"{components[-1]}.md"
        doc_id = item.get("doc_id") or item.get("id")
        if doc_id not in (None, ""):
            path_map[str(doc_id)] = relative_path.as_posix()
    return path_map


def choose_remote_relative_path(
    doc: Dict[str, Any],
    *,
    index_maps: RecordMaps,
    local_maps: RecordMaps,
    toc_path_map: Dict[str, str],
    name_by: str,
) -> str:
    doc_id = str(doc.get("id") or "")
    doc_slug = str(doc.get("slug") or "")

    existing = (
        find_record(index_maps["by_doc_id"], doc_id)
        or find_record(index_maps["by_doc_slug"], doc_slug)
        or find_record(local_maps["by_doc_id"], doc_id)
        or find_record(local_maps["by_doc_slug"], doc_slug)
    )
    if existing and existing.get("relative_path"):
        return str(existing["relative_path"])
    if doc_id and doc_id in toc_path_map:
        return toc_path_map[doc_id]
    return flat_relative_markdown_path(doc, name_by)

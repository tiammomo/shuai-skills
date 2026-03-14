from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import error, parse, request

from .core import DEFAULT_LIMIT, YuqueApiError


def should_retry_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599

def parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, seconds)

def compute_retry_delay(
    attempt: int,
    *,
    base_backoff: float,
    max_backoff: float,
    retry_after: Optional[str],
) -> float:
    header_delay = parse_retry_after(retry_after)
    if header_delay is not None:
        return min(max_backoff, header_delay)
    return min(max_backoff, base_backoff * (2 ** max(0, attempt - 1)))

def get_token(explicit_token: Optional[str]) -> str:
    token = explicit_token or os.environ.get("YUQUE_TOKEN") or os.environ.get("YUQUE_ACCESS_TOKEN")
    if not token:
        raise YuqueApiError(
            "Missing token. Set YUQUE_TOKEN or YUQUE_ACCESS_TOKEN, or pass --token."
        )
    return token

def parse_repo_ref(repo_ref: str) -> Tuple[Optional[str], str]:
    if "/" not in repo_ref:
        return None, repo_ref
    namespace, repo = repo_ref.split("/", 1)
    if not namespace or not repo:
        raise YuqueApiError(f"Invalid repo ref '{repo_ref}'. Use <repo-id> or <namespace>/<repo-slug>.")
    return namespace, repo

def build_repo_path(repo_ref: str) -> str:
    namespace, repo = parse_repo_ref(repo_ref)
    if namespace is None:
        return build_path("repos", repo)
    return build_path("repos", namespace, repo)

def build_path(*segments: str) -> str:
    cleaned = [segment.strip("/") for segment in segments if segment and segment.strip("/")]
    encoded = [parse.quote(segment, safe="") for segment in cleaned]
    return "/" + "/".join(encoded)

class YuqueClient:
    def __init__(
        self,
        *,
        token: str,
        base_url: str,
        timeout: int,
        retries: int,
        retry_backoff: float,
        retry_max_backoff: float,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(0, retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self.retry_max_backoff = max(self.retry_backoff, retry_max_backoff)

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        normalized_path = path if path.startswith("/") else "/" + path
        url = self.base_url + normalized_path
        if query:
            filtered = {
                key: value
                for key, value in query.items()
                if value is not None
            }
            if filtered:
                url += "?" + parse.urlencode(filtered, doseq=True)

        body_bytes = None
        headers = {
            "Accept": "application/json",
            "X-Auth-Token": self.token,
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = request.Request(url, data=body_bytes, method=method.upper(), headers=headers)
        for attempt in range(self.retries + 1):
            try:
                with request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    if not raw:
                        return {"status": resp.status}
                    return decode_response(raw)
            except error.HTTPError as exc:
                if should_retry_status(exc.code) and attempt < self.retries:
                    delay = compute_retry_delay(
                        attempt + 1,
                        base_backoff=self.retry_backoff,
                        max_backoff=self.retry_max_backoff,
                        retry_after=exc.headers.get("Retry-After"),
                    )
                    time.sleep(delay)
                    continue
                raw = exc.read()
                decoded = decode_response(raw) if raw else None
                message = f"{exc.code} {exc.reason}"
                if isinstance(decoded, dict):
                    data = decoded.get("data")
                    error_message = decoded.get("message") or decoded.get("error")
                    if error_message:
                        message = f"{message}: {error_message}"
                    elif isinstance(data, dict) and data.get("message"):
                        message = f"{message}: {data['message']}"
                raise YuqueApiError(
                    message,
                    status=exc.code,
                    payload=decoded,
                    method=method.upper(),
                    path=normalized_path,
                ) from exc
            except error.URLError as exc:
                raise YuqueApiError(f"Network error: {exc.reason}") from exc

def decode_response(raw: bytes) -> Any:
    text = raw.decode("utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}

def unwrap_data(response: Any) -> Any:
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response

def resolve_user(client: YuqueClient, owner: str) -> Dict[str, Any]:
    if owner == "me":
        user = unwrap_data(client.request("GET", build_path("user")))
    else:
        user = unwrap_data(client.request("GET", build_path("users", owner)))
    if not isinstance(user, dict) or not user.get("id"):
        raise YuqueApiError("Unable to resolve user information.")
    return user

def resolve_owner_login(client: YuqueClient, owner: str) -> str:
    return str(resolve_user(client, owner).get("login"))

def iter_owner_repo_paths(owner_login: str, owner_type: str) -> Iterable[str]:
    if owner_type in {"auto", "user"}:
        yield build_path("users", owner_login, "repos")
    if owner_type in {"auto", "group"}:
        yield build_path("groups", owner_login, "repos")

def request_owner_repo_collection(
    client: YuqueClient,
    *,
    owner: str,
    owner_type: str,
    method: str,
    query: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    owner_login = resolve_owner_login(client, owner)
    last_error: Optional[YuqueApiError] = None
    for path in iter_owner_repo_paths(owner_login, owner_type):
        try:
            return client.request(method, path, query=query, payload=payload)
        except YuqueApiError as exc:
            last_error = exc
            if owner_type == "auto" and exc.status == 404:
                continue
            raise
    if last_error:
        raise last_error
    raise YuqueApiError("No owner path available.")

def fetch_all_pages(fetch_page, *, offset: int, limit: int) -> Dict[str, Any]:
    items: List[Any] = []
    pages = 0
    current_offset = offset
    while True:
        response = fetch_page(current_offset, limit)
        data = unwrap_data(response)
        if not isinstance(data, list):
            raise YuqueApiError("Expected a list response while paginating.")
        items.extend(data)
        pages += 1
        if len(data) < limit:
            break
        current_offset += limit
    return {
        "data": items,
        "meta": {
            "all": True,
            "count": len(items),
            "limit": limit,
            "offset": offset,
            "pages": pages,
        },
    }

def fetch_doc_detail(client: YuqueClient, repo_ref: str, doc_ref: str) -> Dict[str, Any]:
    response = client.request(
        "GET",
        build_repo_path(repo_ref) + build_path("docs", str(doc_ref)),
    )
    doc = unwrap_data(response)
    if not isinstance(doc, dict):
        raise YuqueApiError("Expected doc object while fetching doc detail.")
    return doc

def fetch_repo_toc(client: YuqueClient, repo_ref: str) -> List[Dict[str, Any]]:
    try:
        response = client.request("GET", build_repo_path(repo_ref) + build_path("toc"))
    except YuqueApiError as exc:
        if exc.status == 404:
            return []
        raise
    data = unwrap_data(response)
    if not isinstance(data, list):
        raise YuqueApiError("Expected TOC list while fetching repo TOC.")
    return [item for item in data if isinstance(item, dict)]

def fetch_repo_detail(client: YuqueClient, repo_ref: str) -> Dict[str, Any]:
    response = client.request("GET", build_repo_path(repo_ref))
    repo = unwrap_data(response)
    if not isinstance(repo, dict):
        raise YuqueApiError("Expected repo object while fetching repo detail.")
    return repo

def fetch_repo_doc_summaries(client: YuqueClient, repo_ref: str) -> List[Dict[str, Any]]:
    response = fetch_all_pages(
        lambda offset, limit: client.request(
            "GET",
            build_repo_path(repo_ref) + build_path("docs"),
            query={"offset": offset, "limit": limit},
        ),
        offset=0,
        limit=DEFAULT_LIMIT,
    )
    docs = unwrap_data(response)
    if not isinstance(docs, list):
        raise YuqueApiError("Expected doc list while fetching repo docs.")
    return [item for item in docs if isinstance(item, dict)]

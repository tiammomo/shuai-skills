#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import yuque_api


class FakeYuqueClient:
    def __init__(self, docs: Optional[List[Dict[str, Any]]] = None, toc_items: Optional[List[Dict[str, Any]]] = None) -> None:
        self.repo = {
            "id": 101,
            "slug": "repo",
            "name": "Demo Repo",
            "updated_at": "2026-03-14T00:00:00Z",
        }
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.slug_to_id: Dict[str, str] = {}
        self.toc_items = list(toc_items or [])
        self.next_id = 1
        self.repo_put_payloads: List[Dict[str, Any]] = []
        for doc in docs or []:
            self._seed_doc(doc)

    def _seed_doc(self, doc: Dict[str, Any]) -> None:
        doc_id = str(doc.get("id") or self.next_id)
        self.next_id = max(self.next_id, int(doc_id) + 1)
        stored = {
            "id": int(doc_id),
            "slug": str(doc.get("slug") or f"doc-{doc_id}"),
            "title": str(doc.get("title") or f"Doc {doc_id}"),
            "body": str(doc.get("body") or "# Doc\n"),
            "updated_at": str(doc.get("updated_at") or "2026-03-14T00:00:00Z"),
            "public": doc.get("public", 0),
            "format": str(doc.get("format") or "markdown"),
        }
        self.docs[doc_id] = stored
        self.slug_to_id[stored["slug"]] = doc_id

    def _doc_summary(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": doc["id"],
            "slug": doc["slug"],
            "title": doc["title"],
            "updated_at": doc["updated_at"],
            "public": doc["public"],
            "format": doc["format"],
        }

    def _lookup_doc(self, ref: str) -> Optional[Dict[str, Any]]:
        doc = self.docs.get(str(ref))
        if doc is not None:
            return doc
        doc_id = self.slug_to_id.get(str(ref))
        if doc_id is None:
            return None
        return self.docs.get(doc_id)

    def request(self, method: str, path: str, query: Any = None, payload: Any = None) -> Dict[str, Any]:
        if method == "GET" and path == "/ok":
            return {"data": {"ok": True}}
        if path == "/repos/demo/repo":
            if method == "GET":
                return {"data": dict(self.repo)}
            if method == "PUT":
                self.repo_put_payloads.append(dict(payload or {}))
                self.repo["updated_at"] = "2026-03-14T00:10:00Z"
                return {"data": dict(self.repo)}
        if method == "GET" and path == "/repos/demo/repo/toc":
            return {"data": list(self.toc_items)}
        if path == "/repos/demo/repo/docs":
            if method == "GET":
                return {"data": [self._doc_summary(doc) for doc in self.docs.values()]}
            if method == "POST":
                doc_id = self.next_id
                self.next_id += 1
                slug = str((payload or {}).get("slug") or f"doc-{doc_id}")
                stored = {
                    "id": doc_id,
                    "slug": slug,
                    "title": str((payload or {}).get("title") or slug),
                    "body": str((payload or {}).get("body") or (payload or {}).get("body_asl") or ""),
                    "updated_at": "2026-03-14T00:05:00Z",
                    "public": (payload or {}).get("public", 0),
                    "format": str((payload or {}).get("format") or "markdown"),
                }
                self.docs[str(doc_id)] = stored
                self.slug_to_id[slug] = str(doc_id)
                return {"data": dict(stored)}
        if path.startswith("/repos/demo/repo/docs/"):
            ref = path.rsplit("/", 1)[-1]
            doc = self._lookup_doc(ref)
            if doc is None:
                raise yuque_api.YuqueApiError("Not found", status=404, method=method, path=path)
            if method == "GET":
                return {"data": dict(doc)}
            if method == "PUT":
                updated = dict(doc)
                updated.update(payload or {})
                updated["updated_at"] = "2026-03-14T00:06:00Z"
                self.docs[str(updated["id"])] = updated
                self.slug_to_id[str(updated["slug"])] = str(updated["id"])
                return {"data": dict(updated)}
        raise AssertionError((method, path, query, payload))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def hash_markdown_body(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def test_plan_dir_markdown_writes_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "docs"
        root.mkdir()
        (root / "intro.md").write_text("# Intro\n\nHello\n", encoding="utf-8")
        manifest_path = root / "plan.json"
        args = yuque_api.namespace_from_operation(
            {
                "command": "plan-dir-markdown",
                "repo": "demo/repo",
                "root_dir": str(root),
                "write_manifest": str(manifest_path),
            }
        )
        result = yuque_api.perform_command(FakeYuqueClient(), args)
        assert_true(result["meta"]["summary"]["push"] == 1, "Expected one push item in the generated plan.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert_true(manifest["operations"][0]["command"] == "push-markdown", "Manifest should contain a push-markdown operation.")


def test_plan_dir_markdown_includes_review_diff_preview() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "docs"
        root.mkdir()
        local_body = "# Guide\n\nLocal paragraph.\n"
        (root / "guide.md").write_text(
            "---\n"
            "yuque_doc_id: 11\n"
            "yuque_doc_slug: guide\n"
            "title: Guide\n"
            "---\n"
            "\n"
            f"{local_body}",
            encoding="utf-8",
        )
        (root / "yuque-index.json").write_text(
            json.dumps(
                {
                    "repo": "demo/repo",
                    "docs": [
                        {
                            "relative_path": "guide.md",
                            "doc_id": "11",
                            "doc_slug": "guide",
                            "title": "Guide",
                            "content_hash": hash_markdown_body("# Guide\n\nShared baseline.\n"),
                        }
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        args = yuque_api.namespace_from_operation(
            {
                "command": "plan-dir-markdown",
                "repo": "demo/repo",
                "root_dir": str(root),
                "include_diff": True,
                "diff_max_lines": 12,
            }
        )
        result = yuque_api.perform_command(
            FakeYuqueClient(
                docs=[
                    {
                        "id": 11,
                        "slug": "guide",
                        "title": "Guide",
                        "body": "# Guide\n\nRemote paragraph.\n",
                        "updated_at": "2026-03-14T00:08:00Z",
                    }
                ]
            ),
            args,
        )
        assert_true(result["meta"]["summary"]["conflict"] == 1, "Expected one conflict item in the review-heavy plan.")
        review_meta = result["meta"]["review"]
        assert_true(review_meta["manual_review_count"] == 1, "Expected one manual-review item in the review summary.")
        assert_true(review_meta["diff_generated_count"] == 1, "Expected the diff preview to be generated.")
        item = result["data"][0]
        assert_true(item["review"]["recommended_action"] == "manual_review", "Expected the conflict item to recommend manual review.")
        diff_preview = item.get("diff_preview") or {}
        assert_true(diff_preview.get("format") == "unified_diff", "Expected a unified diff preview for the conflict item.")
        preview_text = str(diff_preview.get("preview") or "")
        assert_true("--- local:guide.md" in preview_text, "Expected the diff preview to include the local file header.")
        assert_true("+++ yuque:guide" in preview_text, "Expected the diff preview to include the remote doc header.")
        assert_true("Local paragraph." in preview_text and "Remote paragraph." in preview_text, "Expected the diff preview to include the changed local and remote lines.")


def test_push_dir_markdown_sync_toc_creates_backup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "docs"
        root.mkdir()
        (root / "guide.md").write_text("# Guide\n\nShip it.\n", encoding="utf-8")
        client = FakeYuqueClient()
        args = yuque_api.namespace_from_operation(
            {
                "command": "push-dir-markdown",
                "repo": "demo/repo",
                "source_dir": str(root),
                "sync_toc": True,
            }
        )
        result = yuque_api.perform_command(client, args)
        executed = result["data"]["executed"]
        toc_result = result["data"]["toc"]
        backup = toc_result["backup"]
        snapshot_dir = Path(backup["snapshot_dir"])
        snapshot_metadata = json.loads((snapshot_dir / "snapshot.json").read_text(encoding="utf-8"))
        assert_true(len(executed) == 1, "Expected one markdown file to be pushed.")
        assert_true(executed[0]["status"] == "push", "Expected the executed operation to be a push.")
        assert_true(snapshot_dir.exists(), "Expected the automatic TOC snapshot directory to exist.")
        assert_true((snapshot_dir / "docs" / "guide.md").exists(), "Expected the backup to export markdown files.")
        assert_true((snapshot_dir / "snapshot.json").exists(), "Expected backup metadata to be written.")
        assert_true(snapshot_metadata["schema_version"] == 1, "Expected snapshot metadata to include schema_version.")
        assert_true(len(client.repo_put_payloads) == 1, "Expected exactly one repo TOC update.")
        assert_true("[Guide](guide)" in client.repo_put_payloads[0]["toc"], "Expected the repo TOC payload to include the pushed doc.")


def test_run_manifest_continue_on_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = Path(tmp) / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "continue_on_error": True,
                    "operations": [
                        {"command": "raw", "method": "GET", "path": "/ok"},
                        {"command": "delete-repo", "repo": "demo/repo"},
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        args = yuque_api.namespace_from_operation(
            {
                "command": "run-manifest",
                "manifest": str(manifest_path),
            }
        )
        result = yuque_api.perform_command(FakeYuqueClient(), args)
        assert_true(result["meta"]["failed"] == 1, "Expected one manifest operation failure.")
        assert_true(result["data"][0]["ok"] is True, "Expected the first manifest item to succeed.")
        assert_true(result["data"][1]["ok"] is False, "Expected the second manifest item to fail.")


def test_validate_manifest_rejects_missing_required_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = Path(tmp) / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "operations": [
                        {"command": "push-dir-markdown", "repo": "demo/repo"},
                    ]
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        args = yuque_api.namespace_from_operation(
            {
                "command": "validate-manifest",
                "manifest": str(manifest_path),
            }
        )
        try:
            yuque_api.perform_command(FakeYuqueClient(), args)
        except yuque_api.YuqueApiError as exc:
            assert_true("source_dir" in str(exc), "Expected manifest validation to report the missing source_dir field.")
        else:
            raise AssertionError("Expected validate-manifest to reject incomplete operations.")


def test_prune_guard_blocks_before_backup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "docs"
        root.mkdir()
        (root / "intro.md").write_text("# Intro\n\nHello\n", encoding="utf-8")
        client = FakeYuqueClient(
            docs=[
                {"id": 1, "slug": "intro", "title": "Intro", "body": "# Intro\n\nHello\n"},
                {"id": 2, "slug": "extra", "title": "Extra", "body": "# Extra\n\nOops\n"},
            ]
        )
        try:
            yuque_api.sync_repo_toc_from_local_dir(
                client,
                repo_ref="demo/repo",
                root_dir=root,
                index_file="yuque-index.json",
                write_toc_file=None,
                allow_prune=False,
                backup_dir=None,
                skip_backup=False,
            )
        except yuque_api.YuqueApiError as exc:
            assert_true("Refusing to rewrite the repo TOC" in str(exc), "Expected the prune guard to reject incomplete local trees.")
        else:
            raise AssertionError("Expected sync_repo_toc_from_local_dir to reject missing remote docs.")
        assert_true(not (root.parent / ".yuque-backups").exists(), "Expected backup creation to be skipped when prune guard blocks the TOC rewrite.")
        assert_true(not client.repo_put_payloads, "Expected no repo TOC update when prune guard blocks the operation.")


def test_restore_repo_snapshot_restores_docs_and_toc() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        snapshot_dir = Path(tmp) / "snapshot"
        docs_dir = snapshot_dir / "docs"
        docs_dir.mkdir(parents=True)
        guide_path = docs_dir / "guide.md"
        guide_path.write_text(
            "---\n"
            "yuque_repo: \"demo/repo\"\n"
            "yuque_doc_id: 7\n"
            "yuque_doc_slug: \"guide\"\n"
            "title: \"Guide\"\n"
            "public: 0\n"
            "format: \"markdown\"\n"
            "updated_at: \"2026-03-14T00:00:00Z\"\n"
            "---\n"
            "\n"
            "# Guide\n\nRestored.\n",
            encoding="utf-8",
        )
        (snapshot_dir / "toc.md").write_text("- [Guide](guide)\n", encoding="utf-8")
        snapshot_json = snapshot_dir / "snapshot.json"
        snapshot_json.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "repo": "demo/repo",
                    "snapshot_dir": str(snapshot_dir),
                    "docs_dir": str(docs_dir),
                    "toc_markdown_file": str(snapshot_dir / "toc.md"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        client = FakeYuqueClient()
        args = yuque_api.namespace_from_operation(
            {
                "command": "restore-repo-snapshot",
                "snapshot": str(snapshot_dir),
            }
        )
        result = yuque_api.perform_command(client, args)
        data = result["data"]
        assert_true(data["restored_doc_count"] == 1, "Expected one markdown file to be restored from the snapshot.")
        assert_true(data["toc_restored"] is True, "Expected the snapshot TOC to be restored.")
        assert_true(len(client.repo_put_payloads) == 1, "Expected one TOC update while restoring the snapshot.")
        restored_doc = client._lookup_doc("guide")
        assert_true(restored_doc is not None, "Expected the restored doc to exist after snapshot recovery.")
        assert_true("Restored." in str(restored_doc.get("body") or ""), "Expected the restored markdown body to be uploaded.")


def test_restore_repo_snapshot_dry_run_previews_without_writes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        snapshot_dir = Path(tmp) / "snapshot"
        docs_dir = snapshot_dir / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "guide.md").write_text(
            "---\n"
            "yuque_repo: \"demo/repo\"\n"
            "yuque_doc_id: 7\n"
            "yuque_doc_slug: \"guide\"\n"
            "title: \"Guide\"\n"
            "---\n"
            "\n"
            "# Guide\n\nPreview only.\n",
            encoding="utf-8",
        )
        (snapshot_dir / "toc.md").write_text("- [Guide](guide)\n", encoding="utf-8")
        (snapshot_dir / "snapshot.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "repo": "demo/repo",
                    "snapshot_dir": str(snapshot_dir),
                    "docs_dir": str(docs_dir),
                    "toc_markdown_file": str(snapshot_dir / "toc.md"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        client = FakeYuqueClient()
        args = yuque_api.namespace_from_operation(
            {
                "command": "restore-repo-snapshot",
                "snapshot": str(snapshot_dir),
                "dry_run": True,
            }
        )
        result = yuque_api.perform_command(client, args)
        data = result["data"]
        assert_true(data["dry_run"] is True, "Expected the restore preview to report dry_run=true.")
        assert_true(data["restored_doc_count"] == 1, "Expected one previewed markdown restore.")
        assert_true(data["restored_docs"][0]["action"] == "would_restore", "Expected preview mode to avoid real writes.")
        assert_true(client._lookup_doc("guide") is None, "Expected dry-run to avoid uploading markdown docs.")
        assert_true(not client.repo_put_payloads, "Expected dry-run to avoid updating the repo TOC.")


def main() -> int:
    tests = [
        ("plan-dir-markdown", test_plan_dir_markdown_writes_manifest),
        ("plan-dir-markdown --include-diff", test_plan_dir_markdown_includes_review_diff_preview),
        ("push-dir-markdown --sync-toc", test_push_dir_markdown_sync_toc_creates_backup),
        ("validate-manifest", test_validate_manifest_rejects_missing_required_fields),
        ("run-manifest", test_run_manifest_continue_on_error),
        ("prune-guard", test_prune_guard_blocks_before_backup),
        ("restore-repo-snapshot", test_restore_repo_snapshot_restores_docs_and_toc),
        ("restore-repo-snapshot --dry-run", test_restore_repo_snapshot_dry_run_previews_without_writes),
    ]
    for label, test in tests:
        test()
        print(f"PASS {label}")
    print("All offline Yuque skill self-tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

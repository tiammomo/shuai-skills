# Sync Rules

## Current Scaffold Boundary

- The bundled CLI now supports both planning and a first live tenant-mode execution path.
- `plan-push`, `plan-pull`, and `plan-dir` still describe intended actions before execution.
- `push-markdown`, `replace-markdown`, and `push-dir` perform real Feishu API calls and can modify remote docs immediately.
- `pull-markdown` and `pull-dir` perform real Feishu API calls and write local Markdown files immediately.
- `sync-dir --dry-run` is still the planning surface for mixed sync work.
- `sync-dir --prune --confirm-prune` now performs a guarded prune path with local backups and index cleanup.

## Mapping Sources

The scaffold resolves mapping in this order:

1. Front matter inside the Markdown file
2. Matching entry in `feishu-index.json`
3. Fallback defaults derived from the file path and title

## Recommended Front Matter

Use a small, explicit front matter block:

```yaml
---
title: "Quarterly Plan"
feishu_doc_token: "doxxxxxxxxxxxxxxxxxxxxxxxxxxx"
feishu_folder_token: "fldxxxxxxxxxxxxxxxxxxxxxxxxxx"
feishu_wiki_node_token: ""
feishu_sync_direction: "push"
---
```

Recommended fields:

- `title`: preferred remote title if the first Markdown H1 is absent
- `feishu_doc_token`: target docx document token for update or pull
- `feishu_folder_token`: parent folder token for create flows
- `feishu_wiki_node_token`: wiki node target when the sync is wiki-aware
- `feishu_sync_direction`: `push`, `pull`, or `bidirectional`

## Recommended Directory Index

Use `feishu-index.json` at the sync root for directory jobs.

Current tenant-mode push commands also write back to this file automatically.

Example:

```json
{
  "version": 1,
  "files": [
    {
      "relative_path": "guides/getting-started.md",
      "doc_token": "doxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "title": "Getting Started",
      "content_hash": "sha256:...",
      "last_sync_at": "2026-03-14T10:00:00Z",
      "sync_direction": "push"
    }
  ]
}
```

## Planning Rules

For push plans:

- If `feishu_doc_token` or `doc_token` exists, plan an `update_doc`.
- Else if `feishu_wiki_node_token` exists, plan a `create_or_update_wiki_node`.
- Else if `feishu_folder_token` exists, plan a `create_doc_in_folder`.
- Else plan a `create_doc_in_root`.

For pull plans:

- A pull requires a doc token.
- If no doc token exists, flag the file as blocked instead of guessing a target.

For directory plans:

- The scaffold walks every `*.md` file under the target directory.
- It computes a stable body hash from the local Markdown content.
- It keeps paths relative to the chosen sync root.
- It does not try to infer remote deletes or remote renames yet.

For `sync-dir --dry-run`:

- The command combines local Markdown plans with an app-visible remote folder listing.
- It surfaces remote pull candidates for visible `docx` files that are not already mapped locally.
- With `--prune`, it also surfaces prune candidates when an index-mapped remote doc still exists but the local Markdown file is gone.
- It does not execute writes or deletes yet.

For `sync-dir --prune --confirm-prune`:

- The command rebuilds the same prune candidate set as the dry-run plan.
- It creates a timestamped backup run under `<sync-root>/.feishu-sync-backups` unless `--backup-dir` overrides that location.
- It snapshots the current sync plan and `feishu-index.json` before any remote delete is attempted.
- It exports each prune target to a low-fidelity local backup from `raw_content` before deleting the remote doc.
- It removes only successfully deleted entries from `feishu-index.json`.
- It still does not execute mixed push or pull actions for the remaining plan items.

## Live Push Rules

For `push-markdown`:

- If a doc token already exists, the command uses `replace-markdown` to clear and rewrite the remote document body.
- Existing-doc updates require `--confirm-replace`.
- If no doc token exists, the command creates a new document, appends Markdown content, and writes the returned token back to `feishu-index.json`.
- By default, YAML front matter is stripped before writing.
- Files marked `pull` are skipped unless you pass `--ignore-sync-direction`.
- `body_hash` and `baseline_body_snapshot` now track the Markdown body without front matter so later drift checks and semantic merge suggestions compare the same surface.
- Because a push cannot trust the remote `raw_content` hash without a fresh pull, the stored `remote_content_hash` baseline is cleared on push and rebuilt on the next pull-based inspection.

For `replace-markdown`:

- The current implementation replaces root-level document body content.
- It clears existing root children first, then appends converted Markdown blocks.
- It is intentionally destructive and therefore requires `--confirm-replace`.

For `push-dir`:

- The command walks every `*.md` file under the target directory.
- It reuses the same mapping rules as `plan-dir`.
- It writes or updates `feishu-index.json` incrementally as each file succeeds.
- It skips pull-only files unless `--ignore-sync-direction` is passed.
- It stops on the first failure unless `--continue-on-error` is passed.
- With `--mirror-remote-folders`, files that would otherwise create docs in the root folder derive a remote folder path from the local relative directory.
- With `--mirror-remote-folders --folder-token <fld>`, the supplied folder token is treated as the mirror root, not as a hard per-file override.
- Explicit `feishu_folder_token` or index `folder_token` mappings still win over derived folder paths for that file.
- If `feishu-index.json` maps the same local directory to conflicting folder tokens, `push-dir --mirror-remote-folders` fails before any remote writes.

## Live Pull Rules

For `pull-markdown`:

- The current implementation always fetches document metadata plus `raw_content`.
- With `--fidelity low`, it writes a low-fidelity local Markdown file based on `raw_content`.
- With `--fidelity high`, it also lists the document block tree and rebuilds Markdown for common block types.
- Existing local files require `--overwrite`.
- `--root` and `--index-path` enable `feishu-index.json` write-back automatically.

For `pull-dir`:

- The command walks the visible folder tree and exports every visible `docx` file.
- `--fidelity low` uses `raw_content`; `--fidelity high` reuses the block-tree exporter for each file in the run.
- Existing index mappings win over derived remote paths when deciding where to write local files.
- Otherwise local paths are derived from remote folder names and document titles.
- It writes or updates `feishu-index.json` incrementally as each export succeeds.
- It stops on the first failure unless `--continue-on-error` is passed.

For `sync-dir --dry-run --detect-conflicts`:

- The command reuses the same folder visibility scan as normal dry-run.
- It fetches current remote metadata and `raw_content` for mapped visible docs only.
- It compares the current local body hash to the last synced `body_hash`.
- It compares the current remote revision or `raw_content` hash to the last synced remote baseline.
- It emits review-oriented classifications such as `local_ahead`, `remote_ahead`, `local_and_remote_changed`, and `baseline_incomplete`.
- With `--include-diff`, it also attaches a semantic block preview plus a truncated line diff per inspected mapped file.
- `--diff-fidelity low` builds that preview from a `raw_content`-derived export.
- `--diff-fidelity high` tries a block-tree export for common block types before falling back to `raw_content`.
- `--diff-max-lines` limits the preview size per file so dry-run output remains readable.
- `local_and_remote_changed` items also try to build a semantic merge suggestion from `baseline_body_snapshot`, the current local body, and a comparable remote export body.
- The merge suggestion reports whether the local-only and remote-only semantic changes are non-overlapping enough for an opt-in auto-merge.
- It does not execute push, pull, or prune actions on the strength of those classifications.

For `sync-dir --execute-bidirectional --confirm-bidirectional`:

- The command rebuilds a fresh dry-run conflict plan internally before any write.
- It only acts on files whose current `sync_direction` is `bidirectional`.
- `local_ahead` files are pushed with a remote backup taken first.
- `remote_ahead` files are pulled with a local Markdown backup taken first.
- With `--allow-auto-merge`, `local_and_remote_changed` files can become merge-and-push actions when the semantic merge suggestion says the block changes do not overlap.
- With `--adopt-remote-new`, visible unmapped remote docs become bidirectional pull actions.
- With `--include-create-flow`, unmapped local bidirectional files can create new remote docs and persist the returned mapping.
- `in_sync` files are skipped without writes.
- Any bidirectional file that is review-required, invisible, or missing a doc token blocks the whole run before execution begins.
- `--pull-fidelity` controls the export mode used when a protected pull overwrites the local Markdown file.
- Merge-push actions back up both the local Markdown file and the current remote doc, and restore the local file from backup if the follow-up push fails.

## Title Resolution

The scaffold resolves title in this order:

1. `title` from front matter
2. First Markdown H1
3. File stem with hyphens replaced by spaces

## Commands

Single-file doctor and planning:

- `python scripts/feishu_doc_sync.py doctor`
- `python scripts/feishu_doc_sync.py plan-push path/to/file.md`
- `python scripts/feishu_doc_sync.py plan-pull path/to/file.md`

Single-file live push:

- `python scripts/feishu_doc_sync.py push-markdown path/to/file.md`
- `python scripts/feishu_doc_sync.py replace-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --markdown-file path/to/file.md --confirm-replace`

Single-file live pull:

- `python scripts/feishu_doc_sync.py pull-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --root path/to/exports`
- `python scripts/feishu_doc_sync.py pull-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --root path/to/exports --fidelity high`
- `python scripts/feishu_doc_sync.py upload-media doxxxxxxxxxxxxxxxxxxxxxxxxx path/to/image.png --parent-type docx_image`

Directory planning:

- `python scripts/feishu_doc_sync.py plan-dir path/to/dir`
- `python scripts/feishu_doc_sync.py plan-dir path/to/dir --mode pull`
- `python scripts/feishu_doc_sync.py sync-dir path/to/dir --dry-run`
- `python scripts/feishu_doc_sync.py sync-dir path/to/dir --dry-run --prune`
- `python scripts/feishu_doc_sync.py sync-dir path/to/dir --dry-run --detect-conflicts`
- `python scripts/feishu_doc_sync.py sync-dir path/to/dir --dry-run --detect-conflicts --include-diff`
- `python scripts/feishu_doc_sync.py sync-dir path/to/dir --dry-run --detect-conflicts --include-diff --diff-fidelity high --diff-max-lines 120`

Directory live execution:

- `python scripts/feishu_doc_sync.py push-dir path/to/dir`
- `python scripts/feishu_doc_sync.py push-dir path/to/dir --confirm-replace`
- `python scripts/feishu_doc_sync.py push-dir path/to/dir --folder-token fldxxxxxxxxxxxxxxxxxxxxxxxxx --mirror-remote-folders`
- `python scripts/feishu_doc_sync.py sync-dir path/to/dir --execute-bidirectional --confirm-bidirectional`
- `python scripts/feishu_doc_sync.py sync-dir path/to/dir --execute-bidirectional --confirm-bidirectional --pull-fidelity high`
- `python scripts/feishu_doc_sync.py sync-dir path/to/dir --execute-bidirectional --confirm-bidirectional --allow-auto-merge --adopt-remote-new --include-create-flow`
- `python scripts/feishu_doc_sync.py sync-dir path/to/dir --prune --confirm-prune`
- `python scripts/feishu_doc_sync.py pull-dir path/to/exports`
- `python scripts/feishu_doc_sync.py pull-dir path/to/exports --fidelity high`

## Safe Extension Order

1. Keep front matter and index semantics stable.
2. Keep tenant-mode create, replace, and index write-back stable.
3. Harden prune execution with richer restore tooling and clearer operator review output.
4. Expand media-aware push flows and richer Markdown block coverage.
5. Improve remote pull/export fidelity coverage and restore tooling.
6. Keep conflict detection and bidirectional execution review-first; expand semantic merge coverage only after the planning signals stay stable.

# Sync Rules

## Current Scaffold Boundary

- The bundled CLI now supports both planning and a first live tenant-mode execution path.
- `plan-push`, `plan-pull`, and `plan-dir` still describe intended actions before execution.
- `push-markdown`, `replace-markdown`, and `push-dir` perform real Feishu API calls and can modify remote docs immediately.

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

## Live Push Rules

For `push-markdown`:

- If a doc token already exists, the command uses `replace-markdown` to clear and rewrite the remote document body.
- Existing-doc updates require `--confirm-replace`.
- If no doc token exists, the command creates a new document, appends Markdown content, and writes the returned token back to `feishu-index.json`.
- By default, YAML front matter is stripped before writing.
- Files marked `pull` are skipped unless you pass `--ignore-sync-direction`.

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

Directory planning:

- `python scripts/feishu_doc_sync.py plan-dir path/to/dir`
- `python scripts/feishu_doc_sync.py plan-dir path/to/dir --mode pull`

Directory live push:

- `python scripts/feishu_doc_sync.py push-dir path/to/dir`
- `python scripts/feishu_doc_sync.py push-dir path/to/dir --confirm-replace`

## Safe Extension Order

1. Keep front matter and index semantics stable.
2. Keep tenant-mode create, replace, and index write-back stable.
3. Add media upload and richer Markdown block coverage.
4. Add remote pull/export and higher-fidelity Markdown regeneration.
5. Add conflict detection, diffing, and bidirectional merge last.

# Tenant Mode

## Contents

- [What This Mode Means](#what-this-mode-means)
- [What The App Can See](#what-the-app-can-see)
- [Current Capability In This Repo](#current-capability-in-this-repo)
- [What You Can Do Right Now](#what-you-can-do-right-now)
- [Recommended Workflow](#recommended-workflow)
- [Verification Loop](#verification-loop)
- [Best Fit](#best-fit)
- [Limits](#limits)
- [Commands To Start With](#commands-to-start-with)
- [Current Boundaries](#current-boundaries)
- [Related Docs](#related-docs)

## What This Mode Means

Tenant mode uses `tenant_access_token`, so the app acts as itself.

Use this mode when:

- the sync should run unattended
- the app is the stable identity for the workflow
- the target documents can be explicitly granted to the app
- you do not need the result set to exactly match one person's "My Docs" view

## What The App Can See

In tenant mode, the app can only see documents and folders that are visible to the app identity.

In practice that usually means:

- documents the app created itself
- documents where the app was added as a document app
- folders and resources explicitly granted to the app

This mode does not automatically expose a user's full personal document library.

## Current Capability In This Repo

This repo already has live, real-API capability for tenant mode:

- `tenant-token`
- `validate-tenant`
- `create-document`
- `get-document`
- `get-raw-content`
- `list-folder-files`
- `pull-markdown`
- `pull-dir`
- `sync-dir --dry-run`
- `sync-dir --prune --confirm-prune`
- `append-markdown`
- `replace-markdown`
- `push-markdown`
- `push-dir`
- `list-root-files`
- `delete-document`

These are the parts we already validated against real Feishu APIs in this project.

## What You Can Do Right Now

With the current tenant-mode CLI, you can already:

- verify the app can get a `tenant_access_token`
- create a real cloud document
- fetch document metadata
- fetch the document's plain-text content
- enumerate a specific app-visible folder recursively
- export one app-visible document into low-fidelity local Markdown
- export an app-visible folder tree into low-fidelity local Markdown
- build a dry-run tenant sync plan that surfaces pull candidates, prune candidates, and risk items
- execute guarded prune deletes for index-mapped remote docs that no longer have local Markdown files
- convert local Markdown into Feishu docx blocks and append it into a target document
- replace one existing document body with local Markdown
- push one local Markdown file and write back `feishu-index.json`
- push a Markdown directory and write back `feishu-index.json`
- backfill standalone local Markdown image or attachment lines during append, replace, `push-markdown`, or `push-dir` when `--upload-media` is enabled
- mirror local subdirectories into remote Feishu folders when new docs are created during `push-dir`
- strip YAML front matter from local Markdown files by default before conversion, including UTF-8 BOM files commonly produced on Windows
- enumerate files visible under the app-visible root or a supplied folder token
- delete app-visible test documents when cleanup is needed

This is enough for a solid tenant-mode verification loop and a first real Markdown write path.

## Recommended Workflow

1. Configure `FEISHU_APP_ID` and `FEISHU_APP_SECRET`.
2. Enable required docx and drive scopes for the app.
3. Add the app to each target document when needed.
4. Run `python scripts/feishu_doc_sync.py tenant-token` or `validate-tenant`.
5. Use `list-root-files`, `list-folder-files`, and `get-document` to confirm the app can really see the targets.
6. Use `get-raw-content` or `pull-markdown` to verify the document body that tenant mode actually sees.
7. Use `pull-dir` when you need a low-fidelity local export of the visible remote tree.
8. Use `sync-dir --dry-run` before mixing existing local mappings with remote visibility.
9. Use `sync-dir --prune --confirm-prune` only after reviewing the plan and confirming the backup location.
10. Use `append-markdown`, `replace-markdown`, or `push-markdown` to push local Markdown into the target document.
11. Add `--upload-media` when standalone local Markdown image or attachment lines should become uploaded Feishu image or file blocks during the write.
12. Use `push-dir` when you are ready to execute a directory-level tenant push with index write-back.
13. Add `--mirror-remote-folders` when new docs should land under remote folders derived from the local directory tree.
14. Use `get-raw-content` again to verify the remote result.

## Verification Loop

When expanding tenant mode, use this progression:

1. `tenant-token`
2. `list-root-files`
3. `list-folder-files`
4. `get-document`
5. `get-raw-content`
6. `pull-markdown`
7. `pull-dir`
8. `sync-dir --dry-run`
9. `sync-dir --prune --confirm-prune`
10. `create-document`
11. `append-markdown`
12. `replace-markdown`
13. `push-markdown`
14. `push-dir`
15. `push-dir --folder-token fldxxxxxxxxxxxxxxxxxxxxxxxxx --mirror-remote-folders`
16. `get-raw-content`
17. `delete-document`

That sequence gives you a fast way to prove:

- auth works
- visibility works
- reads work
- writes work
- markdown-to-docx append works
- cleanup works

## Best Fit

Tenant mode is the better default when:

- you want a backend or scheduled sync
- the document set is app-managed
- you want less manual user interaction
- you can curate app permissions document by document

## Limits

- It does not equal a human user's own document visibility.
- If a document is visible in the Feishu UI but not visible to the app, tenant mode will not see it until the app is granted access.
- Root-folder listing reflects the app-visible drive view, not the user's whole library.

## Commands To Start With

```bash
python scripts/feishu_doc_sync.py tenant-token
python scripts/feishu_doc_sync.py validate-tenant
python scripts/feishu_doc_sync.py list-root-files
python scripts/feishu_doc_sync.py list-folder-files --recursive
python scripts/feishu_doc_sync.py get-document doxxxxxxxxxxxxxxxxxxxxxxxxx
python scripts/feishu_doc_sync.py get-raw-content doxxxxxxxxxxxxxxxxxxxxxxxxx
python scripts/feishu_doc_sync.py pull-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --root .\\exports
python scripts/feishu_doc_sync.py pull-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --root .\\exports --fidelity high
python scripts/feishu_doc_sync.py append-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --markdown-file .\\notes.md
python scripts/feishu_doc_sync.py replace-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --markdown-file .\\notes.md --confirm-replace
python scripts/feishu_doc_sync.py upload-media doxxxxxxxxxxxxxxxxxxxxxxxxx .\\diagram.png --parent-type docx_image
python scripts/feishu_doc_sync.py push-markdown path\\to\\file.md
python scripts/feishu_doc_sync.py push-dir path\\to\\dir
python scripts/feishu_doc_sync.py push-dir path\\to\\dir --folder-token fldxxxxxxxxxxxxxxxxxxxxxxxxx --mirror-remote-folders
python scripts/feishu_doc_sync.py pull-dir path\\to\\exports
python scripts/feishu_doc_sync.py pull-dir path\\to\\exports --fidelity high
python scripts/feishu_doc_sync.py sync-dir path\\to\\dir --dry-run
python scripts/feishu_doc_sync.py sync-dir path\\to\\dir --dry-run --detect-conflicts
python scripts/feishu_doc_sync.py sync-dir path\\to\\dir --dry-run --detect-conflicts --include-diff --diff-fidelity high
python scripts/feishu_doc_sync.py sync-dir path\\to\\dir --execute-bidirectional --confirm-bidirectional
python scripts/feishu_doc_sync.py sync-dir path\\to\\dir --execute-bidirectional --confirm-bidirectional --allow-auto-merge --adopt-remote-new --include-create-flow
python scripts/feishu_doc_sync.py sync-dir path\\to\\dir --prune --confirm-prune
```

For cleanup or repeated probes:

```bash
python scripts/feishu_doc_sync.py create-document "Codex Tenant Probe"
python scripts/feishu_doc_sync.py delete-document doxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Current Boundaries

Tenant mode is now strong enough for:

- app-visible inventory checks
- smoke tests for read and write access
- app-visible low-fidelity document export via `raw_content`
- app-visible higher-fidelity document export for common block types via `pull-markdown --fidelity high`
- app-visible low-fidelity or higher-fidelity folder-tree export via `pull-dir`
- dry-run planning for mixed local/remote tenant sync work
- dry-run drift and conflict detection for mapped visible docs
- optional semantic block previews plus truncated line diffs during `sync-dir --dry-run --detect-conflicts`
- semantic merge suggestions for `local_and_remote_changed` items when a baseline snapshot is available
- protected bidirectional execution for already mapped clean bidirectional doc pairs
- opt-in protected execution for safe semantic auto-merge, unmapped remote adoption, and local create flow in bidirectional mode
- guarded prune execution for index-mapped remote docs with local backups and index cleanup
- explicit media upload into docx workflows with returned `file_token`
- standalone local Markdown media backfill into Feishu image or file blocks during write flows when `--upload-media` is enabled
- app-visible Markdown append into existing docs
- app-visible document body replacement for existing docs
- app-visible single-file push with automatic `feishu-index.json` write-back
- app-visible directory push with automatic `feishu-index.json` write-back
- app-visible directory push with optional remote folder mirroring for create flows
- app-visible Markdown append from local files without leaking default YAML front matter into the remote doc body
- verifying plain-text content after remote writes
- cleaning up remote probe documents

Tenant mode in this repo still does not yet cover:

- user-personal visibility
- automatic resolution for overlapping or ambiguous bidirectional conflicts
- round-trip fidelity guarantees for every block type
- richer inline-media rewrite beyond standalone Markdown lines and broader embedded asset round-tripping

## Related Docs

- [auth.md](./auth.md)
- [token.md](./token.md)
- [sync-rules.md](./sync-rules.md)

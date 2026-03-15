---
name: feishu-doc-sync
description: Live workflow for validating and syncing local Markdown with Feishu cloud documents. Use when Codex needs to inspect Feishu auth and scopes, map `.md` files to Feishu docx documents, append or replace Markdown in tenant-visible docs, upload document media, write back `feishu-index.json`, mirror local directory trees into remote Feishu folders during directory pushes, run selectable-fidelity pull/export planning, or continue extending the bundled Feishu sync skill.
---

# Feishu Doc Sync

Use the bundled Python CLI to inspect prerequisites, validate live auth and docx connectivity, and execute the current tenant-mode Markdown sync path for Feishu document workflows. The current repo version can already fetch tenant tokens, create or inspect docs, read raw content, append Markdown, replace document body content, upload media into docx contexts, push one file, push a directory, mirror local folders into remote Feishu folders for new docs, pull low- or high-fidelity Markdown exports, and write back `feishu-index.json`.

## Safety First

- Prefer `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, and access tokens from the environment.
- Treat app secrets, access tokens, document tokens, and folder tokens as sensitive.
- Pick one identity model per run: app-visible sync with `tenant_access_token`, or user-visible sync with `user_access_token`.
- Do not assume API scope approval is enough. Feishu doc access also requires the app or user to be granted access to the target document.
- For tenant-level automation, confirm the app has been added to each target document or folder before attempting writes.
- Keep destructive overwrite or remote delete logic behind explicit user confirmation when extending this scaffold.

## Task Router

- Work in app-scoped sync mode where the app sees only documents granted to the app:
  Read [references/tenant-mode.md](./references/tenant-mode.md).
- Work in user-scoped sync mode where Feishu permissions should follow one user account:
  Read [references/user-mode.md](./references/user-mode.md).
- Check required Feishu scopes, token expectations, or permission setup:
  Read [references/auth.md](./references/auth.md) and [references/token.md](./references/token.md).
- Validate live tenant auth or docx connectivity:
  Use `python scripts/feishu_doc_sync.py tenant-token`, `validate-tenant`, `create-document`, `get-document`, `get-raw-content`, `list-root-files`, `list-folder-files`, or `delete-document`, then read [references/auth.md](./references/auth.md).
- Append or replace Markdown in one existing tenant-visible doc:
  Use `python scripts/feishu_doc_sync.py append-markdown` or `replace-markdown`, then read [references/tenant-mode.md](./references/tenant-mode.md) and [references/sync-rules.md](./references/sync-rules.md).
- Push one local Markdown file and update `feishu-index.json`:
  Use `python scripts/feishu_doc_sync.py push-markdown <file>`, then read [references/sync-rules.md](./references/sync-rules.md).
- Push a whole Markdown directory and update `feishu-index.json`:
  Use `python scripts/feishu_doc_sync.py push-dir <dir>`; add `--mirror-remote-folders` when new docs should inherit a remote folder tree derived from the local directory layout, then read [references/sync-rules.md](./references/sync-rules.md).
- Pull one Feishu document into local Markdown:
  Use `python scripts/feishu_doc_sync.py pull-markdown <doc>`; add `--fidelity high` when common block types should be rebuilt from the Feishu block tree, then read [references/pull-export.md](./references/pull-export.md) and [references/sync-rules.md](./references/sync-rules.md).
- Pull a visible Feishu folder tree into a local Markdown directory:
  Use `python scripts/feishu_doc_sync.py pull-dir <dir>`; add `--fidelity high` for block-tree exports, then read [references/pull-export.md](./references/pull-export.md).
- Upload one local image or attachment into a Feishu document workflow:
  Use `python scripts/feishu_doc_sync.py upload-media <doc> <path>`, then read [references/markdown-mapping.md](./references/markdown-mapping.md) and [references/tenant-mode.md](./references/tenant-mode.md).
- Build a directory sync dry-run before any destructive tenant sync extension:
  Use `python scripts/feishu_doc_sync.py sync-dir <dir> --dry-run`; add `--detect-conflicts` when mapped docs should be classified for local drift, remote drift, and review-required conflicts, then read [references/pull-export.md](./references/pull-export.md), [references/sync-rules.md](./references/sync-rules.md), and [references/conflict-rules.md](./references/conflict-rules.md).
- Execute explicit prune for index-mapped remote docs whose local Markdown files are gone:
  Use `python scripts/feishu_doc_sync.py sync-dir <dir> --prune --confirm-prune`, then read [references/pull-export.md](./references/pull-export.md), [references/sync-rules.md](./references/sync-rules.md), and [references/conflict-rules.md](./references/conflict-rules.md).
- Build or finish a user login flow:
  Use `python scripts/feishu_doc_sync.py user-auth-url`, `exchange-user-token`, or `authorize-local`, then read [references/token.md](./references/token.md).
- Plan sync for one markdown file:
  Use `python scripts/feishu_doc_sync.py plan-push <file>` or `plan-pull <file>`, then read [references/sync-rules.md](./references/sync-rules.md).
- Plan sync for a markdown directory:
  Use `python scripts/feishu_doc_sync.py plan-dir <dir>`, then read [references/sync-rules.md](./references/sync-rules.md).
- Decide how Markdown should map into Feishu docx blocks:
  Read [references/markdown-mapping.md](./references/markdown-mapping.md).
- Need direct official doc entry points for Feishu auth, docx, drive, or media APIs:
  Read [references/official-docs.md](./references/official-docs.md).
- Diagnose unsupported round-trips, conflict handling, or scope failures:
  Read [references/conflict-rules.md](./references/conflict-rules.md) and [references/troubleshooting.md](./references/troubleshooting.md).

## Default Workflow

1. Run `python scripts/feishu_doc_sync.py doctor`.
2. Choose the identity model first: app-visible sync via `tenant_access_token`, or user-visible sync via `user_access_token`.
3. Validate the chosen auth path and confirm the app or user can access the target docs.
4. Add front matter or `feishu-index.json` mappings locally.
5. Generate a single-file or directory plan before running live sync.
6. For one remote document export, use `pull-markdown`.
7. For one file push, use `push-markdown`.
8. For one existing document body overwrite, use `replace-markdown` with `--confirm-replace`.
9. For one directory, use `pull-dir`, `push-dir`, `push-dir --mirror-remote-folders`, `sync-dir --dry-run`, `sync-dir --dry-run --detect-conflicts`, or `sync-dir --prune --confirm-prune` depending on whether you are exporting, writing, mirroring the local folder tree, planning, classifying drift, or pruning remote docs with backups.
10. Extend richer block coverage, Markdown media round-tripping, diffing, and user-mode sync only after the current tenant-mode mapping, prune safeguards, and permission model are stable.

## Reference Files

- [references/auth.md](./references/auth.md): Feishu app model, scopes, document sharing requirements, and official permission links.
- [references/token.md](./references/token.md): which token to use, how to obtain it, and which official auth endpoints matter for this skill.
- [references/tenant-mode.md](./references/tenant-mode.md): app-scoped sync model for documents that are visible to the Feishu app.
- [references/user-mode.md](./references/user-mode.md): user-scoped sync model for documents that should follow one user's own Feishu visibility.
- [references/sync-rules.md](./references/sync-rules.md): local mapping rules, front matter fields, planning behavior, and current push execution rules.
- [references/pull-export.md](./references/pull-export.md): selectable-fidelity pull behavior, output-path rules, folder traversal, and sync-dir planning or prune execution semantics.
- [references/markdown-mapping.md](./references/markdown-mapping.md): Markdown subset guidance, convert-to-block workflow, high-fidelity export notes, and media upload notes.
- [references/conflict-rules.md](./references/conflict-rules.md): source-of-truth rules, conflict detection suggestions, and safe defaults.
- [references/troubleshooting.md](./references/troubleshooting.md): common scope, share, token, and rate-limit failures.
- [references/official-docs.md](./references/official-docs.md): curated official Feishu documentation links for auth, docx, drive, and media APIs.

## Bundled Resources

- `scripts/feishu_doc_sync.py`: CLI for auth validation, tenant-mode doc read/write operations, explicit doc-media upload, folder-aware `push-dir`, selectable-fidelity pull/export, sync-dir prune execution with backups, drift/conflict dry-runs, and local planning flows.
- `scripts/check_feishu_skill.py`: local smoke check for the scaffold.

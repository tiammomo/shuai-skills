# Tenant Mode

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
- convert local Markdown into Feishu docx blocks and append it into a target document
- replace one existing document body with local Markdown
- push one local Markdown file and write back `feishu-index.json`
- push a Markdown directory and write back `feishu-index.json`
- strip YAML front matter from local Markdown files by default before conversion, including UTF-8 BOM files commonly produced on Windows
- enumerate files visible under the app-visible root or a supplied folder token
- delete app-visible test documents when cleanup is needed

This is enough for a solid tenant-mode verification loop and a first real Markdown write path.

## Recommended Workflow

1. Configure `FEISHU_APP_ID` and `FEISHU_APP_SECRET`.
2. Enable required docx and drive scopes for the app.
3. Add the app to each target document when needed.
4. Run `python scripts/feishu_doc_sync.py tenant-token` or `validate-tenant`.
5. Use `list-root-files` and `get-document` to confirm the app can really see the targets.
6. Use `get-raw-content` to verify the document body that tenant mode actually sees.
7. Use `append-markdown`, `replace-markdown`, or `push-markdown` to push local Markdown into the target document.
8. Use `push-dir` when you are ready to execute a directory-level tenant push with index write-back.
9. Use `get-raw-content` again to verify the remote result.

## Verification Loop

When expanding tenant mode, use this progression:

1. `tenant-token`
2. `list-root-files`
3. `get-document`
4. `get-raw-content`
5. `create-document`
6. `append-markdown`
7. `replace-markdown`
8. `push-markdown`
9. `push-dir`
10. `get-raw-content`
11. `delete-document`

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
python scripts/feishu_doc_sync.py get-document doxxxxxxxxxxxxxxxxxxxxxxxxx
python scripts/feishu_doc_sync.py get-raw-content doxxxxxxxxxxxxxxxxxxxxxxxxx
python scripts/feishu_doc_sync.py append-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --markdown-file .\\notes.md
python scripts/feishu_doc_sync.py replace-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --markdown-file .\\notes.md --confirm-replace
python scripts/feishu_doc_sync.py push-markdown path\\to\\file.md
python scripts/feishu_doc_sync.py push-dir path\\to\\dir
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
- app-visible Markdown append into existing docs
- app-visible document body replacement for existing docs
- app-visible single-file push with automatic `feishu-index.json` write-back
- app-visible directory push with automatic `feishu-index.json` write-back
- app-visible Markdown append from local files without leaking default YAML front matter into the remote doc body
- verifying plain-text content after remote writes
- cleaning up remote probe documents

Tenant mode in this repo still does not yet cover:

- user-personal visibility
- recursive document tree sync execution
- rich block diffing or round-trip fidelity checks
- media upload and richer embedded asset handling

## Related Docs

- [auth.md](./auth.md)
- [token.md](./token.md)
- [sync-rules.md](./sync-rules.md)

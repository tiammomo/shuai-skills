# User Mode

## What This Mode Means

User mode uses `user_access_token`, so the app acts with one specific Feishu user's identity.

Use this mode when:

- the visible document set must follow a real user's own permissions
- you want to work with documents from that user's personal view
- tenant mode cannot see the documents you need
- an interactive authorization step is acceptable

## What The User Token Can Represent

In user mode, Feishu visibility follows the backing user account rather than the app identity.

This is the mode to use when you want access that more closely matches:

- that user's personal document library
- that user's shares and memberships
- documents the user can open even when the app itself cannot

## Current Capability In This Repo

This repo now supports the auth side of user mode plus protected single-document and directory-level sync paths:

- `user-auth-url`
- `exchange-user-token`
- `authorize-local`
- `validate-user`
- `get-document --auth-mode user`
- `get-raw-content --auth-mode user`
- `list-root-files --auth-mode user`
- `list-folder-files --auth-mode user`
- `pull-markdown --auth-mode user`
- `pull-dir --auth-mode user`
- `append-markdown --auth-mode user --confirm-user-write`
- `replace-markdown --auth-mode user --confirm-user-write --confirm-replace`
- `push-markdown --auth-mode user --confirm-user-write`
- `push-dir --auth-mode user --confirm-user-write`
- `push-dir --auth-mode user --confirm-user-write --allow-user-create`
- `sync-dir --auth-mode user --dry-run`
- `sync-dir --auth-mode user --dry-run --detect-conflicts`
- `sync-dir --auth-mode user --execute-bidirectional --confirm-bidirectional --confirm-user-write`
- `sync-dir --auth-mode user --execute-bidirectional --confirm-bidirectional --confirm-user-write --include-create-flow --allow-user-create`

That means the scaffold can now obtain `user_access_token`, validate user-visible connectivity, inspect user-visible docs, export user-visible Markdown, and perform protected single-document or directory-level writes as that user.

So the current status is:

- user auth flow: scaffolded
- user token acquisition: supported
- user-token-based document listing and export: supported
- user-token-based single-document append/replace/push: supported behind explicit confirmation flags
- user-token-based directory push: supported behind `--confirm-user-write`
- user-token-based sync-dir dry-run and conflict review: supported
- user-token-based protected bidirectional sync execution: supported for mapped docs, opt-in create flow, and user-visible pull candidates
- user-token-based prune delete: still tenant-only

## Recommended Workflow

1. Configure `FEISHU_APP_ID` and `FEISHU_APP_SECRET`.
2. Configure a valid OAuth `redirect_uri` in Feishu app login settings.
3. Generate an auth URL with `user-auth-url`.
4. Let the user approve access.
5. Exchange the returned code within 5 minutes.
6. Store `FEISHU_USER_ACCESS_TOKEN` securely for the next user-scoped API steps.
7. Run `validate-user` before the first real read to confirm the token can see the target doc.
8. Use `get-document`, `list-root-files`, `pull-markdown`, or `pull-dir` with `--auth-mode user` for user-visible reads and exports.
9. For one protected write, use `append-markdown`, `replace-markdown`, or `push-markdown` with `--auth-mode user --confirm-user-write`.
10. For one directory push, use `push-dir --auth-mode user --confirm-user-write`; add `--allow-user-create` only when unmapped local files should create new user-visible remote docs.
11. For one directory plan, use `sync-dir --auth-mode user --dry-run`; add `--detect-conflicts` when mapped docs should be classified for drift and review.
12. For protected bidirectional execution, use `sync-dir --auth-mode user --execute-bidirectional --confirm-bidirectional --confirm-user-write`.
13. Keep `--confirm-replace` for destructive replacements, and add `--allow-user-create` only when an unmapped local file should create a new user-visible remote doc.

## Best Fit

User mode is the better choice when:

- the sync should mirror one person's own document visibility
- you need access to documents already shared with that user
- app-level visibility is too narrow
- manual authorization is acceptable

## Limits

- It requires an OAuth authorization step.
- The auth code is single-use and expires after 5 minutes.
- A valid `redirect_uri` is still required.
- User mode remote delete and prune execution are still tenant-only.
- `push-markdown --auth-mode user` defaults to updating an already mapped doc; creating a new remote doc still requires explicit `--allow-user-create`.
- `push-dir --auth-mode user` also defaults to updating already mapped docs unless `--allow-user-create` is present.
- `sync-dir --auth-mode user --execute-bidirectional` still requires both `--confirm-bidirectional` and `--confirm-user-write`.
- `sync-dir --auth-mode user --include-create-flow` still requires explicit `--allow-user-create`.

## Commands To Start With

```bash
python scripts/feishu_doc_sync.py user-auth-url --redirect-uri https://example.com/callback
python scripts/feishu_doc_sync.py exchange-user-token your_auth_code --redirect-uri https://example.com/callback
```

If a valid local or public callback is available:

```bash
python scripts/feishu_doc_sync.py authorize-local
```

Once `FEISHU_USER_ACCESS_TOKEN` is available:

```bash
python scripts/feishu_doc_sync.py validate-user --document-id doxxxxxxxxxxxxxxxxxxxxxxxxx
python scripts/feishu_doc_sync.py list-root-files --auth-mode user
python scripts/feishu_doc_sync.py pull-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --auth-mode user --root ./exports
python scripts/feishu_doc_sync.py replace-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --auth-mode user --confirm-user-write --confirm-replace --content "# Updated"
python scripts/feishu_doc_sync.py push-markdown ./notes.md --auth-mode user --confirm-user-write --confirm-replace
python scripts/feishu_doc_sync.py push-dir ./notes --auth-mode user --confirm-user-write --confirm-replace
python scripts/feishu_doc_sync.py sync-dir ./notes --auth-mode user --dry-run --detect-conflicts
python scripts/feishu_doc_sync.py sync-dir ./notes --auth-mode user --execute-bidirectional --confirm-bidirectional --confirm-user-write
```

## Related Docs

- [auth.md](./auth.md)
- [token.md](./token.md)
- [official-docs.md](./official-docs.md)

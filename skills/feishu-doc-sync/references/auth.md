# Auth and Permissions

## Recommended App Model

- Start with a custom Feishu app for internal Markdown sync jobs.
- Store `FEISHU_APP_ID` and `FEISHU_APP_SECRET` in the environment.
- Prefer `tenant_access_token` for unattended, app-visible sync jobs.
- Use `user_access_token` only when the sync must follow one user's own document membership.
- Keep one identity model per run. Do not mix tenant-visible and user-visible expectations in the same command chain.

## Mode Split

This skill documents two operating modes:

- tenant mode: sync documents that are visible to the app
  Read [tenant-mode.md](./tenant-mode.md).
- user mode: sync documents that are visible to one Feishu user
  Read [user-mode.md](./user-mode.md).

Choose the mode before enabling scopes or debugging visibility, because Feishu exposes different document sets to each token type.

## Required Environment

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_BASE_URL` only when you need a non-default endpoint
- `FEISHU_REDIRECT_URI` only for user-token OAuth flows
- `FEISHU_TENANT_ACCESS_TOKEN` or `FEISHU_USER_ACCESS_TOKEN` only when you intentionally want to inject a pre-fetched token

For token acquisition details and official auth endpoints, read [token.md](./token.md).

## Current CLI Coverage

The current skill already supports these live command groups:

Tenant auth and tenant-visible probes:

- `python scripts/feishu_doc_sync.py doctor`
- `python scripts/feishu_doc_sync.py tenant-token`
- `python scripts/feishu_doc_sync.py validate-tenant`
- `python scripts/feishu_doc_sync.py create-document "Connectivity Check"`
- `python scripts/feishu_doc_sync.py get-document doxxxxxxxxxxxxxxxxxxxxxxxxx`
- `python scripts/feishu_doc_sync.py get-raw-content doxxxxxxxxxxxxxxxxxxxxxxxxx`
- `python scripts/feishu_doc_sync.py list-root-files`
- `python scripts/feishu_doc_sync.py delete-document doxxxxxxxxxxxxxxxxxxxxxxxxx`

Tenant write flows:

- `python scripts/feishu_doc_sync.py append-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --markdown-file .\notes.md`
- `python scripts/feishu_doc_sync.py replace-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --markdown-file .\notes.md --confirm-replace`
- `python scripts/feishu_doc_sync.py push-markdown .\docs\notes.md`
- `python scripts/feishu_doc_sync.py push-dir .\docs`

User-token OAuth helpers:

- `python scripts/feishu_doc_sync.py user-auth-url --redirect-uri https://example.com/callback`
- `python scripts/feishu_doc_sync.py exchange-user-token your_auth_code --redirect-uri https://example.com/callback`
- `python scripts/feishu_doc_sync.py authorize-local`

Planning helpers:

- `python scripts/feishu_doc_sync.py plan-push .\docs\notes.md`
- `python scripts/feishu_doc_sync.py plan-pull .\docs\notes.md`
- `python scripts/feishu_doc_sync.py plan-dir .\docs --mode push`

## Stable Output Contract

The CLI now uses one predictable top-level JSON shape for direct commands:

- `ok`
- `command`
- `mode`
- `base_url`
- `token_source` when a tenant token is involved
- `official_docs`
- `request`
- `auth` when the command first resolves tenant auth
- `result`
- `error` only when the command fails
- `notes`

Nested payloads under `result` may still be command-specific, but the top-level contract is now stable enough for higher-level automation and smoke checks.

## Scope Matrix

Minimal write sync without media:

- `docx:document`
  This single scope already covers create, read, and block write for docx documents.
- Or use the granular pair `docx:document:create` and `docx:document:write_only` if you want narrower write permissions.

Read or pull workflows:

- `docx:document:readonly`
- Or keep `docx:document` if the same app also writes.

Markdown or HTML to block conversion:

- `docx:document.block:convert`

Images or attachments inside a docx document:

- `docs:document.media:upload`

Folder-aware sync:

- `space:folder:create`
- `space:document:retrieve`
- `drive:drive.metadata:readonly`

Wiki-backed targets:

- `wiki:node:read`
- `wiki:node:create`
- `wiki:node:update`

## Non-Scope Access Requirements

Having a scope is not enough to read or write a specific document.

When using `tenant_access_token`:

- The official docx API pages state that the app still needs document access.
- Add the app to the target document from the document UI:
  `...` -> `More` -> `Add document app`
- If the app cannot be found in that picker, confirm the app already has at least one cloud-doc or bitable API scope enabled and that the latest permissions have been published.

When using `user_access_token`:

- The user behind the token must already have access to the target document.
- Share the document with that user from the document's share dialog before testing pull or push calls.

When creating a document inside a folder:

- The create-document page notes that if you use `tenant_access_token`, `folder_token` can only point at folders created by the app.

## OAuth Notes For User Tokens

The current scaffold follows the newer Feishu OAuth documentation:

- [Obtain OAuth code](https://open.feishu.cn/document/authentication-management/access-token/obtain-oauth-code)
- [Get user_access_token](https://open.feishu.cn/document/authentication-management/access-token/get-user-access-token)

Practical consequences:

- the authorization code is valid for 5 minutes
- `authorize-local` waits 300 seconds by default
- `exchange-user-token` exchanges the code directly with `client_id` and `client_secret`
- the `redirect_uri` must exactly match the value configured in the Feishu app login settings

## Recommended Live Validation Order

1. Run `doctor` and confirm app credentials are visible.
2. Run `tenant-token`.
3. Run `validate-tenant`.
4. Create one disposable document with `create-document`.
5. Read it with `get-document` and `get-raw-content`.
6. Write into it with `append-markdown`.
7. Confirm overwrite safeguards with `replace-markdown --confirm-replace`.
8. Move to `push-markdown` and `push-dir` only after the single-document path is stable.

This keeps scope, visibility, Markdown conversion, and index write-back debugging separate enough to isolate failures.

## How To Enable In Feishu

1. Create or open the target app in the Feishu developer console.
2. Open the app's permission or scope management page.
3. Enable the scopes from the matrix above.
4. Save the changes and, if your release flow requires it, publish the updated app version before testing.
5. Separately grant document access to the app or user token identity on every target document or folder.

## Example Assets

Reusable examples live under [../assets/examples/](../assets/examples/):

- [../assets/examples/sample-sync-root/feishu-index.json](../assets/examples/sample-sync-root/feishu-index.json)
- [../assets/examples/sample-sync-root/new-doc.md](../assets/examples/sample-sync-root/new-doc.md)
- [../assets/examples/sample-sync-root/existing-doc.md](../assets/examples/sample-sync-root/existing-doc.md)

Use them as starting points for `push-markdown`, `push-dir`, front matter, and index-mapping experiments.

## Official Sources

- [Choose which token type to use](https://open.feishu.cn/document/uAjLw4CM/ugTN1YjL4UTN24CO1UjN/trouble-shooting/how-to-choose-which-type-of-token-to-use)
- [Obtain OAuth code](https://open.feishu.cn/document/authentication-management/access-token/obtain-oauth-code)
- [Get user_access_token](https://open.feishu.cn/document/authentication-management/access-token/get-user-access-token)
- [Create document](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/create?lang=zh-CN)
- [Get document](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/get?lang=zh-CN)
- [Get raw content](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/raw_content?lang=zh-CN)
- [Create blocks](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block-children/create?lang=zh-CN)
- [Convert Markdown or HTML to blocks](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/convert?lang=zh-CN)
- [Upload media](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/media/upload_all)
- [Create folder](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/file/create_folder)

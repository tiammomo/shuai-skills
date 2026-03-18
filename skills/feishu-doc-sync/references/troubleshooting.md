# Troubleshooting

## Contents

- [Missing App Credentials Or Token Inputs](#missing-app-credentials-or-token-inputs)
- [`20029 redirect_uri` Request Is Invalid](#20029-redirect_uri-request-is-invalid)
- [Tenant Auth Succeeds But The Document Is Still Invisible](#tenant-auth-succeeds-but-the-document-is-still-invisible)
- [`403` Or `1770032` Forbidden While Reading Or Writing](#403-or-1770032-forbidden-while-reading-or-writing)
- [Create Document Fails When `folder_token` Is Set](#create-document-fails-when-folder_token-is-set)
- [`replace-markdown` Refuses To Run](#replace-markdown-refuses-to-run)
- [`push-markdown` Or `push-dir` Partially Succeeds](#push-markdown-or-push-dir-partially-succeeds)
- [Read Works But Block Writes Hit Rate Limits](#read-works-but-block-writes-hit-rate-limits)
- [Markdown Convert Followed By Block Insert Fails](#markdown-convert-followed-by-block-insert-fails)
- [Pull Fidelity Looks Poor](#pull-fidelity-looks-poor)
- [Secret Was Pasted Into Chat Or Shell History](#secret-was-pasted-into-chat-or-shell-history)

## Missing App Credentials Or Token Inputs

Symptoms:

- `Missing required value: use --app-id or set FEISHU_APP_ID`
- `Missing required value: use --app-secret or set FEISHU_APP_SECRET`
- tenant commands fail before any Feishu API call

Checks:

- confirm `FEISHU_APP_ID` and `FEISHU_APP_SECRET` are visible in the shell running the CLI
- rerun `python scripts/feishu_doc_sync.py doctor`
- if you intentionally inject a token, confirm `FEISHU_TENANT_ACCESS_TOKEN` or `FEISHU_USER_ACCESS_TOKEN` is present

## `20029 redirect_uri` Request Is Invalid

This is the most common real OAuth failure for `user_access_token`.

Meaning:

- Feishu rejected the OAuth callback address before issuing the authorization code

Checks:

- make sure you are configuring an OAuth login redirect URI, not an event-subscription callback URL
- use the same `redirect_uri` value in `user-auth-url` and `exchange-user-token`
- confirm the configured value exactly matches the redirect URI in the Feishu app login settings
- remember that the authorization code is valid for only 5 minutes

## Tenant Auth Succeeds But The Document Is Still Invisible

Common symptom:

- `validate-tenant` succeeds
- `get-document` or `list-root-files` still cannot see the document you can see in the Feishu UI

Meaning:

- app auth is working
- document-level access is still missing

Checks:

- add the app to the target document with `Add document app`
- publish the latest permission changes in the Feishu developer console
- remember that `tenant_access_token` only sees app-visible resources, not the entire user-visible document library

## `403` Or `1770032` Forbidden While Reading Or Writing

Meaning:

- scope approval alone is not enough
- the app or user token identity still lacks access to that document or folder

Checks:

- if you use `tenant_access_token`, add the app to the document
- if you use `user_access_token`, share the document with the backing user account
- verify the needed scope is enabled:
  `docx:document`, `docx:document:readonly`, or `docx:document.block:convert`

## Create Document Fails When `folder_token` Is Set

The create-document API notes a tenant-token restriction:

- with `tenant_access_token`, the folder must be one created by the app

If you need broader folder placement:

- switch the workflow to a user token that has access
- or create the folder through the app first
- or omit `folder_token` and let Feishu create in the default app-visible location

## `replace-markdown` Refuses To Run

Expected failure:

- `replace-markdown is destructive. Re-run with --confirm-replace ...`

Meaning:

- the safeguard is working

Fix:

- rerun with `--confirm-replace` only after confirming you want to clear the existing remote body first

This same safeguard is also enforced by `push-markdown` and `push-dir` when a mapping already points at an existing document.

## `push-markdown` Or `push-dir` Partially Succeeds

What to expect:

- `push-markdown` writes to Feishu first, then updates `feishu-index.json`
- `push-dir` processes files one by one and returns per-file results

Checks:

- inspect the per-file `result` objects in the JSON output
- confirm whether the file was skipped because `sync_direction` is `pull`
- confirm whether the failure happened during create, replace, or index write-back
- use `--continue-on-error` only when partial completion is acceptable

If `push-dir` stops early without `--continue-on-error`, that is expected behavior.

## Read Works But Block Writes Hit Rate Limits

Feishu docx docs call out separate rate limits for create, block insert, delete, and batch update flows.

Symptoms:

- temporary failures after rapid repeated writes
- responses with retry-oriented error payloads such as `99991400`

Mitigation:

- reduce concurrency
- avoid hammering the same document repeatedly
- back off and retry after a delay

## Markdown Convert Followed By Block Insert Fails

One table-related caveat from the official convert guide:

- remove `merge_info` from converted table blocks before nested insertion because that field is read-only

The current skill already strips `merge_info` during block insertion. If you extend the converter path, keep that behavior.

## Pull Fidelity Looks Poor

That is expected if you only use `raw_content`.

Meaning:

- `raw_content` is a quick plain-text view, not a lossless Markdown export

Use:

- `raw_content` for drift checks and quick verification
- block-tree reconstruction for higher-fidelity pull/export work

## Secret Was Pasted Into Chat Or Shell History

If the app secret was exposed:

- rotate the app secret in Feishu first
- update `FEISHU_APP_SECRET`
- only then run live auth or document calls again

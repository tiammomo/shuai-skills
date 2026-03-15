# Token Guide

## Which Token To Use

For Feishu document sync, the practical choices are:

- `tenant_access_token`
  Best for unattended internal automation where the app acts as itself.
- `user_access_token`
  Best when the sync must act with a real user's document membership and sharing permissions.

Usually do not use `app_access_token` directly for docx sync calls.

- In this skill, `app_access_token` is only useful for low-level auth diagnostics.
- The docx and drive APIs used by this skill should be called with either `tenant_access_token` or `user_access_token`.

## Recommended Default

For the first internal Feishu sync implementation in this repo:

- prefer a self-built app
- prefer `tenant_access_token` for backend or scheduled sync
- switch to `user_access_token` only when document membership must follow a specific user

## Mode Quick Pick

- If the job should sync documents visible to the app:
  Read [tenant-mode.md](./tenant-mode.md) and prefer `tenant_access_token`.
- If the job should sync documents visible to one user:
  Read [user-mode.md](./user-mode.md) and plan around `user_access_token`.

## Current CLI Commands

The scaffold currently includes these auth-oriented commands:

- `python scripts/feishu_doc_sync.py tenant-token`
  Fetches a fresh `tenant_access_token` for a self-built app.
- `python scripts/feishu_doc_sync.py validate-tenant`
  Reuses `FEISHU_TENANT_ACCESS_TOKEN` if present, or fetches a new tenant token and validates connectivity.
- `python scripts/feishu_doc_sync.py user-auth-url --redirect-uri https://example.com/callback`
  Builds a browser authorization URL for the Feishu user login flow.
- `python scripts/feishu_doc_sync.py exchange-user-token your_auth_code --redirect-uri https://example.com/callback`
  Exchanges the returned authorization code for `user_access_token` credentials.
- `python scripts/feishu_doc_sync.py authorize-local`
  Starts a temporary local callback server, opens the auth page, captures the returned code, and exchanges it automatically.

For a doc-level probe, add:

```bash
python scripts/feishu_doc_sync.py validate-tenant --document-id doxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Self-Built App Token Docs

Self-built app app token:

- API: `POST /open-apis/auth/v3/app_access_token/internal`
- Doc: [Get app_access_token for a self-built app](https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/auth-v3/auth/app_access_token_internal)

Self-built app tenant token:

- API: `POST /open-apis/auth/v3/tenant_access_token/internal`
- Doc: [Get tenant_access_token for a self-built app](https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/auth-v3/auth/tenant_access_token_internal)

## User Token Docs

The current user-token flow for this scaffold is based on the newer Feishu OAuth documentation you referenced:

- OAuth code guide: [Obtain OAuth code](https://open.feishu.cn/document/authentication-management/access-token/obtain-oauth-code)
- User token guide: [Get user_access_token](https://open.feishu.cn/document/authentication-management/access-token/get-user-access-token)

According to those official pages:

- the authorization code is valid for 5 minutes
- the token exchange uses `POST /open-apis/authen/v2/oauth/token`
- the request should include `grant_type`, `client_id`, `client_secret`, and `code`

That means the current scaffold now exchanges the auth code directly with app credentials. It does not require an intermediate `app_access_token` for `exchange-user-token`.

Authorization entry points used by this scaffold:

- Default URL pattern used by `user-auth-url`:
  `https://open.feishu.cn/open-apis/authen/v1/authorize?app_id=...&redirect_uri=...&state=...`

This authorize URL is still based on a live endpoint probe against the official Feishu domain. The login docs are JS-rendered, so the exact authorize path is still treated as an implementation inference rather than a quoted static snippet from the docs page.

Local callback helper:

- `authorize-local` defaults to `http://127.0.0.1:16666/callback`
- the default wait window is now `300` seconds so it matches the official 5-minute code lifetime
- the local server is temporary, but the redirect URI still needs to match the Feishu app login configuration exactly
- if you change the local port or path, update the app login redirect URI to the same value before retrying

Legacy user-token references kept for compatibility research:

- [OIDC v1 get user_access_token](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/oidc-access_token/create)
- [OIDC v1 refresh user_access_token](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/oidc-refresh_access_token/create)
- [v1 get user_access_token](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/access_token/create)
- [v1 refresh user_access_token](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/refresh_access_token/create)

## Token Selection Reference

Official guidance:

- [How to choose which type of token to use](https://open.feishu.cn/document/uAjLw4CM/ugTN1YjL4UTN24CO1UjN/trouble-shooting/how-to-choose-which-type-of-token-to-use)

Use it when deciding whether a sync job should run as:

- the app itself
- a tenant-scoped backend job
- a user-scoped interactive sync

## What To Put In Env Vars

Recommended local env mapping for this scaffold:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_REDIRECT_URI`
- `FEISHU_APP_ACCESS_TOKEN`
- `FEISHU_TENANT_ACCESS_TOKEN`
- `FEISHU_USER_ACCESS_TOKEN`

Recommended usage:

- set only one of `FEISHU_TENANT_ACCESS_TOKEN` or `FEISHU_USER_ACCESS_TOKEN` per run
- if the live implementation later fetches tokens dynamically, keep only `FEISHU_APP_ID` and `FEISHU_APP_SECRET`

PowerShell example:

```powershell
$env:FEISHU_APP_ID='cli_xxx'
$env:FEISHU_APP_SECRET='your-rotated-secret'
$env:FEISHU_REDIRECT_URI='https://example.com/callback'
python .\skills\feishu-doc-sync\scripts\feishu_doc_sync.py tenant-token
python .\skills\feishu-doc-sync\scripts\feishu_doc_sync.py user-auth-url
```

Code exchange example:

```powershell
python .\skills\feishu-doc-sync\scripts\feishu_doc_sync.py exchange-user-token your_auth_code
```

Local callback example:

```powershell
python .\skills\feishu-doc-sync\scripts\feishu_doc_sync.py authorize-local
```

## Practical Decision Table

If the job is a scheduled internal sync:

- use a self-built app
- obtain `tenant_access_token`

If the job must respect a particular user's document access:

- run an auth flow for that user
- obtain `user_access_token`

If you are only checking app-level auth plumbing:

- `app_access_token` may still be useful to validate the auth setup
- but do not assume it is the token accepted by the document sync APIs

## Important Feishu Constraint

Even with the correct token type:

- `tenant_access_token` still requires the app to be granted access to the target document
- `user_access_token` still requires the user to be granted access to the target document

That sharing requirement is separate from token acquisition.

## Secret Safety

- Prefer environment variables over command-line flags for `app_secret`.
- If an app secret has been pasted into chat, logs, or shell history, rotate it before using this scaffold for real requests.

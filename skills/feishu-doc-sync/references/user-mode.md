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

This repo currently supports the auth side of user mode:

- `user-auth-url`
- `exchange-user-token`
- `authorize-local`

That means the scaffold can help obtain `user_access_token`, but the document read/list/sync commands in this repo are still primarily implemented around tenant mode today.

So the current status is:

- user auth flow: scaffolded
- user token acquisition: supported
- user-token-based document listing and sync execution: still the next implementation step

## Recommended Workflow

1. Configure `FEISHU_APP_ID` and `FEISHU_APP_SECRET`.
2. Configure a valid OAuth `redirect_uri` in Feishu app login settings.
3. Generate an auth URL with `user-auth-url`.
4. Let the user approve access.
5. Exchange the returned code within 5 minutes.
6. Store `FEISHU_USER_ACCESS_TOKEN` securely for the next user-scoped API steps.

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
- The current repo does not yet expose a full set of user-token-powered document list/read/sync commands.

## Commands To Start With

```bash
python scripts/feishu_doc_sync.py user-auth-url --redirect-uri https://example.com/callback
python scripts/feishu_doc_sync.py exchange-user-token your_auth_code --redirect-uri https://example.com/callback
```

If a valid local or public callback is available:

```bash
python scripts/feishu_doc_sync.py authorize-local
```

## Related Docs

- [auth.md](./auth.md)
- [token.md](./token.md)
- [official-docs.md](./official-docs.md)

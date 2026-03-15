# Conflict Rules

## Default Stance

- Do not auto-merge local Markdown and remote Feishu edits in the first live version.
- Choose a source of truth per run and make the plan explicit.

## Recommended Modes

Push mode:

- Local Markdown wins.
- Remote changes since the last sync should be flagged for review, not silently overwritten.

Pull mode:

- Remote Feishu doc wins.
- Local unsynced edits should be flagged before writing back to disk.

## Suggested Conflict Inputs

When you extend the scaffold, compare at least:

- local content hash
- last known remote revision ID
- last known remote content hash when a revision baseline is missing
- last sync timestamp
- current mode (`push` or `pull`)

## What The Current Scaffold Does

- It computes local hashes.
- It surfaces whether a local file already has a mapped doc token.
- It writes `body_hash`, `remote_revision_id`, and `remote_content_hash` back into `feishu-index.json` as sync baselines.
- `sync-dir --dry-run --detect-conflicts` fetches current remote metadata and `raw_content` for mapped visible docs.
- It classifies `local_ahead`, `remote_ahead`, `local_and_remote_changed`, and `baseline_incomplete` states.
- It does not attempt delete propagation.

## Current Dry-Run Conflict Detection

Use:

```bash
python scripts/feishu_doc_sync.py sync-dir .\docs --dry-run --detect-conflicts
```

Current comparison model:

- compare the current local Markdown body hash to the last synced `body_hash`
- compare the current remote revision or `raw_content` hash to the last synced remote baseline
- map the result through the file's current `sync_direction`

Current recommended actions:

- `push_candidate`: only the local file changed since the last baseline
- `pull_candidate`: only the remote doc changed since the last baseline
- `review_before_push` or `review_before_pull`: the requested direction would overwrite newer changes on the other side
- `manual_conflict_review`: both sides changed
- `rebuild_sync_baseline`: the index is missing enough state to trust conflict detection yet

Treat this as a planning and review surface, not an execution engine. It does not write local files or remote docs.

## Safe Resolution Patterns

- Pull remote content into a separate review branch or temp file before overwrite.
- Duplicate the target Feishu doc before a risky bulk rewrite.
- Require explicit approval before any future `--prune-remote` or `--delete-local` behavior.

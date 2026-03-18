# Conflict Rules

## Contents

- [Default Stance](#default-stance)
- [Recommended Modes](#recommended-modes)
- [Suggested Conflict Inputs](#suggested-conflict-inputs)
- [What The Current Scaffold Does](#what-the-current-scaffold-does)
- [Current Dry-Run Conflict Detection](#current-dry-run-conflict-detection)
- [Current Diff Preview Surface](#current-diff-preview-surface)
- [Protected Bidirectional Execution](#protected-bidirectional-execution)
- [Safe Resolution Patterns](#safe-resolution-patterns)

## Default Stance

- Do not auto-merge local Markdown and remote Feishu edits by default.
- Choose a source of truth per run and make the plan explicit.
- Only allow semantic auto-merge as an explicit opt-in when a reusable sync baseline exists and the detected block changes do not overlap.

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
- It writes `body_hash`, `baseline_body_snapshot`, `remote_revision_id`, and `remote_content_hash` back into `feishu-index.json` as sync baselines.
- `sync-dir --dry-run --detect-conflicts` fetches current remote metadata and `raw_content` for mapped visible docs.
- With `--include-diff`, it also loads the local Markdown body and builds a semantic block preview plus a truncated line diff against a comparable remote export body.
- `--diff-fidelity low` compares against a `raw_content`-derived export, while `--diff-fidelity high` tries a block-tree export first and falls back to `raw_content` if needed.
- It classifies `local_ahead`, `remote_ahead`, `local_and_remote_changed`, and `baseline_incomplete` states.
- `local_and_remote_changed` items can now include a semantic three-way merge suggestion derived from the stored baseline snapshot.
- `sync-dir --execute-bidirectional --confirm-bidirectional` can still execute clean `local_ahead` and `remote_ahead` items directly, and can optionally add semantic auto-merge, unmapped remote adoption, or local create flow through explicit flags.
- It still does not attempt delete propagation or broad automatic merge outside that protected opt-in surface.

## Current Dry-Run Conflict Detection

Use:

```bash
python scripts/feishu_doc_sync.py sync-dir .\docs --dry-run --detect-conflicts
python scripts/feishu_doc_sync.py sync-dir .\docs --dry-run --detect-conflicts --include-diff --diff-fidelity high
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

Treat the dry-run as a planning and review surface. Protected execution exists, but broad auto-merge is still not the default.

## Current Diff Preview Surface

When `--include-diff` is enabled:

- each inspected mapped file gets a `diff` object in the dry-run result
- the top-level preview is semantic-block-oriented so headings, paragraphs, lists, quotes, and code changes are easier to review quickly
- the same `diff` object also includes a truncated `line_preview` for exact Markdown inspection
- `--diff-max-lines` caps how many diff lines are returned per file
- `--diff-fidelity high` can surface a closer structural comparison for common Feishu block types, but it is still review-oriented and not a round-trip guarantee
- `local_and_remote_changed` items also expose a `merge_suggestion` object when a baseline snapshot is available, including whether a safe auto-merge is ready and a preview of the semantic keep-local / keep-remote decisions
- the preview helps review `manual_conflict_review`, `review_before_push`, and `review_before_pull` cases without turning `sync-dir` into an execution engine

## Protected Bidirectional Execution

Use:

```bash
python scripts/feishu_doc_sync.py sync-dir .\docs --execute-bidirectional --confirm-bidirectional
python scripts/feishu_doc_sync.py sync-dir .\docs --execute-bidirectional --confirm-bidirectional --allow-auto-merge --adopt-remote-new --include-create-flow
```

Current protection model:

- it rebuilds a fresh conflict plan before any write
- it only executes files whose `sync_direction` is `bidirectional`
- it only pushes `local_ahead` files and only pulls `remote_ahead` files
- with `--allow-auto-merge`, it can also push a semantically merged local body for `local_and_remote_changed` files when the stored baseline proves the block changes do not overlap
- with `--adopt-remote-new`, visible unmapped remote docs become bidirectional pull targets
- with `--include-create-flow`, unmapped local bidirectional files can create new remote docs and write back the returned mapping
- it blocks the whole run if any bidirectional file still needs review, is invisible, or is missing a doc mapping
- it backs up the current remote document before protected push
- it backs up the current local Markdown file before protected pull
- it backs up both sides before a semantic merge push, and restores the local file from backup if the follow-up push fails after the merged body is written locally

Current safety boundary:

- it still does not auto-resolve overlapping semantic conflicts
- it still does not create new mappings or adopt remote docs unless the operator explicitly opts into those execution modes
- it still does not attempt delete propagation or free-form semantic merge beyond the protected non-overlapping case

## Safe Resolution Patterns

- Pull remote content into a separate review branch or temp file before overwrite.
- Duplicate the target Feishu doc before a risky bulk rewrite.
- Require explicit approval before any future `--prune-remote` or `--delete-local` behavior.

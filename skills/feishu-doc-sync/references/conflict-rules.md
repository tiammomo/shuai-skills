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
- last sync timestamp
- current mode (`push` or `pull`)

## What The Current Scaffold Does

- It computes local hashes.
- It surfaces whether a local file already has a mapped doc token.
- It does not fetch remote revision IDs yet.
- It does not attempt delete propagation.

## Safe Resolution Patterns

- Pull remote content into a separate review branch or temp file before overwrite.
- Duplicate the target Feishu doc before a risky bulk rewrite.
- Require explicit approval before any future `--prune-remote` or `--delete-local` behavior.

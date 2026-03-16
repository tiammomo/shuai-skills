# Pull and Export

## Current Pull Boundary

The current tenant-mode pull path now supports two fidelity levels:

Today the CLI supports:

- `pull-markdown`
- `pull-dir`
- `upload-media`
- `sync-dir --dry-run`
- `sync-dir --prune --confirm-prune`

Export modes:

- `--fidelity low`: use Feishu `raw_content` for plain-text recovery and simple drift checks
- `--fidelity high`: rebuild Markdown from the Feishu block tree for common block types such as headings, paragraphs, lists, quotes, code blocks, todos, callouts, files, and basic image references

High-fidelity export is still best-effort. Unsupported block types are left behind as HTML comments so the export remains reviewable instead of silently dropping content.

## `pull-markdown`

Use `pull-markdown` when you already know the target document token.

Example:

```bash
python scripts/feishu_doc_sync.py pull-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --root .\exports
python scripts/feishu_doc_sync.py pull-markdown doxxxxxxxxxxxxxxxxxxxxxxxxx --root .\exports --fidelity high
```

Current behavior:

- fetch document metadata
- fetch `raw_content`
- optionally fetch the full block tree when `--fidelity high` is selected
- build a local Markdown file with front matter
- optionally update `feishu-index.json`

Default front matter includes:

- `title`
- `feishu_doc_token`
- `feishu_sync_direction`
- `feishu_pull_fidelity: raw_content` or `feishu_pull_fidelity: blocks`

Safety rules:

- existing files are not overwritten unless `--overwrite` is set
- `--root` or `--index-path` enables index write-back automatically
- `--relative-path` lets you control the local output path under `--root`
- high-fidelity export still depends on Feishu block coverage, so treat unsupported-block comments as a review signal instead of a hard failure

## `pull-dir`

Use `pull-dir` when you want to export every app-visible docx file under a folder tree.

Example:

```bash
python scripts/feishu_doc_sync.py pull-dir .\exports --folder-token fldxxxxxxxxxxxxxxxxxxxxxxxxx
python scripts/feishu_doc_sync.py pull-dir .\exports --folder-token fldxxxxxxxxxxxxxxxxxxxxxxxxx --fidelity high
```

Current behavior:

- resolves the starting folder token or root folder
- traverses the folder tree
- exports each visible `docx` file to local Markdown
- creates local directories from remote folder names
- writes or updates `feishu-index.json`
- reuses the same fidelity mode for every exported document in the run

Output-path rules:

- existing index mappings win first
- otherwise local paths are derived from remote folder names and doc titles
- names are sanitized for Windows-safe local paths
- collisions are disambiguated with a token-based suffix

## `sync-dir --dry-run`

Use `sync-dir --dry-run` before extending tenant mode into prune or mixed push/pull execution.

Example:

```bash
python scripts/feishu_doc_sync.py sync-dir .\docs --dry-run --prune
python scripts/feishu_doc_sync.py sync-dir .\docs --dry-run --detect-conflicts --include-diff --diff-fidelity high
```

Current dry-run output includes:

- local file plans
- remote folder-listing summary
- remote pull candidates
- prune candidates from missing local files that still have mapped remote docs
- risk items such as invisible mapped docs and pull-only local files
- optional conflict-detection results for mapped visible docs when `--detect-conflicts` is enabled
- optional semantic block previews plus truncated line diffs for inspected mapped docs when `--include-diff` is enabled
- semantic merge suggestions for `local_and_remote_changed` items when the index already stores a reusable baseline body snapshot

Current safety boundary:

- protected bidirectional execution now supports clean bidirectional pairs by default, with opt-in merge, adopt, and create expansion modes
- `--prune` only surfaces candidates, it does not delete anything
- conflict detection is still review-first; broad auto-pull, auto-push, and auto-merge are not the default
- diff previews are body-oriented review aids, not semantic block merges or round-trip guarantees

## `sync-dir --execute-bidirectional --confirm-bidirectional`

Use `sync-dir --execute-bidirectional --confirm-bidirectional` when:

- the local and remote document are already mapped through front matter or `feishu-index.json`
- the file's `sync_direction` is `bidirectional`
- the last sync baseline is complete enough for conflict detection
- you want clean `local_ahead` items pushed and clean `remote_ahead` items pulled without hand-running each file

Example:

```bash
python scripts/feishu_doc_sync.py sync-dir .\docs --execute-bidirectional --confirm-bidirectional
python scripts/feishu_doc_sync.py sync-dir .\docs --execute-bidirectional --confirm-bidirectional --pull-fidelity high
python scripts/feishu_doc_sync.py sync-dir .\docs --execute-bidirectional --confirm-bidirectional --allow-auto-merge --adopt-remote-new --include-create-flow
```

Current behavior:

- rebuilds a fresh conflict plan before any execution
- blocks the run when any bidirectional file still needs manual review
- backs up the current remote doc before protected push
- backs up the current local Markdown file before protected pull
- can auto-merge and push a `local_and_remote_changed` file only when the semantic merge suggestion says the baseline, local, and remote changes do not overlap
- can adopt visible unmapped remote docs into local Markdown plus `feishu-index.json` when `--adopt-remote-new` is enabled
- can create new remote docs from unmapped local bidirectional files when `--include-create-flow` is enabled
- updates `feishu-index.json` through the existing push and pull execution paths

Current safety boundary:

- it does not create new bidirectional mappings or adopt remote docs unless you opt into those execution modes
- it does not auto-resolve overlapping conflicts
- it does not semantically merge local and remote Markdown beyond the protected non-overlapping case

## `sync-dir --prune --confirm-prune`

Use `sync-dir --prune --confirm-prune` when:

- a remote doc is still mapped in `feishu-index.json`
- the local Markdown file has been removed from the sync root
- you want a backup-first remote prune instead of leaving stale docs behind

Example:

```bash
python scripts/feishu_doc_sync.py sync-dir .\docs --prune --confirm-prune
```

Current behavior:

- rebuilds the prune candidate set from the same folder visibility scan used by dry-run
- creates a timestamped backup run under `.feishu-sync-backups` unless overridden
- snapshots the current plan and `feishu-index.json`
- exports each prune target from `raw_content` before delete
- deletes the remote docx file
- removes successful prune entries from `feishu-index.json`

Current safety boundary:

- backup export is still low fidelity because it uses `raw_content`
- mixed push/pull execution is still not implemented

## `upload-media`

Use `upload-media` when a local image or attachment should be pushed into a Feishu document workflow before richer Markdown media mapping is automated.

Example:

```bash
python scripts/feishu_doc_sync.py upload-media doxxxxxxxxxxxxxxxxxxxxxxxxx .\diagram.png --parent-type docx_image
```

Current behavior:

- uploads one local file through the Feishu multipart media API
- defaults to `parent_type=docx_image`
- returns the Feishu `file_token`
- optionally forwards `extra.drive_route_token` when a routed upload path is needed

Current safety boundary:

- the command uploads media but does not yet rewrite Markdown image references automatically
- downstream block insertion still has to decide how uploaded `file_token` values become image or attachment blocks

## Recommended Usage Order

1. `list-folder-files`
2. `pull-markdown`
3. `pull-dir`
4. `sync-dir --dry-run`
5. `sync-dir --execute-bidirectional --confirm-bidirectional` when the reviewed bidirectional plan is clean
6. `sync-dir --prune --confirm-prune` when a reviewed prune plan should be executed
7. `upload-media` when the job needs image or attachment tokens before richer push automation lands

## Next Planned Improvements

- broader block-tree export coverage with fewer unsupported placeholders
- automatic Markdown image and attachment wiring on push
- richer remote restore artifacts for prune backups
- richer semantic merge guidance on top of the current semantic preview
- broader bidirectional execution across unmapped remote pull candidates and safer create flows

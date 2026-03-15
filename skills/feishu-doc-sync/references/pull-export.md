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
```

Current dry-run output includes:

- local file plans
- remote folder-listing summary
- remote pull candidates
- prune candidates from missing local files that still have mapped remote docs
- risk items such as invisible mapped docs and pull-only local files
- optional conflict-detection results for mapped visible docs when `--detect-conflicts` is enabled

Current safety boundary:

- mixed push/pull execution is not implemented yet
- `--prune` only surfaces candidates, it does not delete anything
- conflict detection is review-only; it does not auto-pull, auto-push, or auto-merge

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
5. `sync-dir --prune --confirm-prune` when a reviewed prune plan should be executed
6. `upload-media` when the job needs image or attachment tokens before richer push automation lands

## Next Planned Improvements

- broader block-tree export coverage with fewer unsupported placeholders
- automatic Markdown image and attachment wiring on push
- richer remote restore artifacts for prune backups
- mixed push/pull execution across mirrored folder trees

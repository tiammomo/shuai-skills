# Directory Sync Workflows

## Contents

- [Use Cases](#use-cases)
- [Source Of Truth Rules](#source-of-truth-rules)
- [Command Patterns](#command-patterns)
- [Path And Identity Rules](#path-and-identity-rules)
- [Conflict Planning Rules](#conflict-planning-rules)
- [Output And Index Files](#output-and-index-files)

## Use Cases

- Use `push-dir-markdown` when the local markdown tree is the source of truth for doc bodies.
- Use `pull-dir-markdown` when the local directory should mirror a Yuque repo.
- Use `plan-dir-markdown` before bulk syncs when both sides may have changed.
- Use `export-repo-markdown` instead of directory sync when the task is backup or migration without TOC reconstruction.

## Source Of Truth Rules

- `push-dir-markdown` executes only the `push` operations from a generated sync plan.
- `pull-dir-markdown` executes only the `pull` operations from a generated sync plan.
- `plan-dir-markdown` exposes `push`, `pull`, `skip`, and `conflict` items before anything is written.
- Existing doc identity comes from front matter first, then `yuque-index.json`.

## Command Patterns

- `push-dir-markdown <repo> <source-dir>` recursively scans local `*.md` files and uploads only planned changes.
- `pull-dir-markdown <repo> <output-dir>` recreates the remote hierarchy locally and always writes front matter plus `yuque-index.json`.
- `plan-dir-markdown <repo> <root-dir>` emits a reviewable manifest and can persist it with `--write-manifest`.
- `push-dir-markdown --sync-toc` first performs the planned uploads, then rewrites the remote TOC from the local tree.

## Path And Identity Rules

- New docs derive a stable slug from the relative file path by default.
- Switch to `--slug-source stem` only when file stems are already globally unique.
- `pull-dir-markdown` uses the remote TOC to rebuild nested local paths.
- Parent docs with children land as `<parent>/index.md`; leaf docs land as `<name>.md`.
- By default those local names come from document titles, not slugs.
- Existing `yuque-index.json` mappings and local front matter doc ids or slugs take precedence over TOC-derived relocation so repeated pulls do not churn paths.
- Use `--name-by slug` or `--name-by id` only when the local repo needs machine-oriented filenames instead of readable titles.

## Conflict Planning Rules

- `plan-dir-markdown` compares local content hashes, remote content hashes, and the last synced hash stored in `yuque-index.json`.
- When `yuque-index.json` exists, its stored `content_hash` acts as the base version for three-way comparison.
- When no index entry exists, the planner falls back to local front matter doc identity and `updated_at`.
- If only the local side changed since the base, the plan emits `push`.
- If only the remote side changed since the base, the plan emits `pull`.
- If both sides changed since the base, the plan emits `conflict`.
- If local and remote hashes already match, the plan emits `skip`.

## Output And Index Files

- `push-dir-markdown` and `pull-dir-markdown` both refresh `<root>/yuque-index.json`.
- Each index entry keeps `relative_path`, `doc_id`, `doc_slug`, `title`, `public`, `format`, `updated_at`, `content_hash`, and `last_sync_at`.
- `plan-dir-markdown --write-manifest sync-plan.json` writes an object with an `operations` array ready for `run-manifest`.
- The plan preview paths follow the same default title-based hierarchy as `pull-dir-markdown`, so review output matches the eventual local tree.

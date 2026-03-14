# Troubleshooting

## Contents

- [Auth And Access](#auth-and-access)
- [Repo Or Doc Not Found](#repo-or-doc-not-found)
- [Unexpected Create Instead Of Update](#unexpected-create-instead-of-update)
- [TOC Sync Refused To Run](#toc-sync-refused-to-run)
- [Backup Questions](#backup-questions)
- [Restoring From Snapshot](#restoring-from-snapshot)
- [Directory Sync Conflicts](#directory-sync-conflicts)
- [Path Churn Or Filename Surprises](#path-churn-or-filename-surprises)
- [Manifest Failures](#manifest-failures)

## Auth And Access

- If every request fails immediately, verify `YUQUE_TOKEN` or `YUQUE_ACCESS_TOKEN` first.
- If the token was pasted into chat or logs, rotate it before automating further.
- Start with `python scripts/yuque_api.py me` to confirm the token still works.

## Repo Or Doc Not Found

- If `list-repos --owner <login>` fails for a team space, retry with `--owner-type group` or leave it on `auto`.
- If a doc lookup unexpectedly 404s, check whether the manifest or front matter is carrying an old `yuque_doc_id` or `yuque_doc_slug`.
- Prefer discovering refs with `list-repos` or `list-docs` before writing a large manifest by hand.

## Unexpected Create Instead Of Update

- `push-markdown` creates a new doc when the lookup target does not exist.
- Round-trip sync works best when the local file includes front matter produced by `pull-markdown --front-matter` or `export-repo-markdown --front-matter`.
- For directory sync, verify that `yuque-index.json` is still aligned with the local tree before bulk pushes.

## TOC Sync Refused To Run

- This usually means the remote repo still has docs that are missing from the local markdown tree.
- Pull the repo first, or confirm that the local tree is intentionally incomplete before using `--allow-prune`.
- The prune guard triggers before the backup and before the `PUT /repos/...` TOC update, so refusal here is a protection, not a partial write.

## Backup Questions

- Automatic snapshots run before `sync-dir-toc` and before `push-dir-markdown --sync-toc`, unless `--skip-backup` is passed.
- The default location is a sibling `.yuque-backups/<namespace>__<repo>/<timestamp>/` directory.
- If you need a different location, pass `--backup-dir <path>`.
- Each snapshot contains exported markdown under `docs/`, plus `repo.json`, `toc.json`, `toc.md`, and `snapshot.json`.

## Restoring From Snapshot

- Use `restore-repo-snapshot <snapshot-dir>` or point it directly at `snapshot.json`.
- Use `--dry-run` first when the recovery is high-stakes and you want to preview doc count and TOC impact before any writes happen.
- If the command says the snapshot repo and `--repo` differ, re-run with `--allow-repo-override` only when that target change is intentional.
- `--skip-docs` restores only the TOC; `--skip-toc` restores only the markdown docs.
- If restore fails with an unsupported schema version, the snapshot was produced by a newer backup format than this skill currently understands.
- Snapshot restore replays markdown exports, so it is best for recovering content and hierarchy after sync mistakes, not for reconstructing original non-markdown payload formats exactly.

## Directory Sync Conflicts

- `plan-dir-markdown` emits `conflict` when both local and remote content changed since the last synced base hash.
- If there is no prior index entry, the planner falls back to front matter doc identity and `updated_at`, which is less reliable than a fresh `yuque-index.json`.
- When a repo may have changed on both sides, review the plan first instead of jumping straight to `push-dir-markdown` or `pull-dir-markdown`.

## Path Churn Or Filename Surprises

- `pull-dir-markdown` defaults to title-based local names, which are readable but can change if titles change.
- `yuque-index.json` and front matter mappings take precedence over TOC-derived relocation, so repeated pulls should settle once the index is stable.
- For brand-new docs, the default `--slug-source path` is safer than `stem` when different folders share the same file name.

## Manifest Failures

- `run-manifest` stops on the first error unless either the manifest root object or the CLI flag enables `continue_on_error`.
- Each manifest operation must be a JSON object with a `command` field.
- `validate-manifest` is the quickest way to catch missing required fields, unsupported keys, and invalid option values before the batch starts.
- Use the templates under `assets/manifests/` as a starting point when hand-writing a batch job.
- Use `python scripts/check_yuque_skill.py` when you want a one-shot local health check of the skill before or after refactors.
- Batch commands now emit progress to `stderr`, so it is normal to see per-step counters while the structured result continues to come back on `stdout`.

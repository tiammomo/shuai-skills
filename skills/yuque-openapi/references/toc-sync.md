# TOC Sync And Backup Rules

## Contents

- [When To Use](#when-to-use)
- [TOC Payload Shape](#toc-payload-shape)
- [Safety Guards](#safety-guards)
- [Backup Behavior](#backup-behavior)
- [Restore Behavior](#restore-behavior)
- [Recommended Workflow](#recommended-workflow)

## When To Use

- Use `sync-dir-toc` when document bodies are already correct and only the remote hierarchy should be rebuilt.
- Use `push-dir-markdown --sync-toc` when the local markdown tree is the source of truth for both content and hierarchy.

## TOC Payload Shape

Update repo TOC with Markdown outline links rather than the raw `toc_yml` response shape:

```json
{
  "toc": "- [Parent](parent-slug)\n  - [Child](child-slug)\n"
}
```

Rules:

- Use Markdown outline links such as `- [Parent](parent-slug)`.
- Indent children with two spaces.
- Resolve each local markdown file to a Yuque doc through front matter, `yuque-index.json`, or an unambiguous remote match.

## Safety Guards

- By default TOC sync refuses to proceed if the remote repo still contains docs that are missing from the local tree.
- Re-run with `--allow-prune` only when removing those remote docs from the TOC is intentional.
- Treat TOC rewrites as source-of-truth operations. If the local tree is incomplete, pull the repo first instead of forcing `--allow-prune`.

## Backup Behavior

- Before the remote TOC changes, the CLI exports an automatic snapshot unless `--skip-backup` is passed.
- The default snapshot location is a sibling `.yuque-backups/<namespace>__<repo>/<timestamp>/` directory.
- The snapshot contains repo markdown exports with front matter under `docs/`, plus `repo.json`, `toc.json`, `toc.md`, and `snapshot.json`.
- `snapshot.json` now includes an explicit `schema_version` so future restore logic can validate compatibility.
- Use `--backup-dir <path>` to move the snapshot somewhere else.
- Use `--write-toc-file <path>` to inspect the generated TOC markdown before upload.

## Restore Behavior

- Use `restore-repo-snapshot <snapshot-dir-or-json>` to restore docs and/or the TOC from one of those automatic snapshots.
- By default the command restores both markdown docs and `toc.md` back into the repo recorded in `snapshot.json`.
- Pass `--dry-run` to preview which markdown files would be replayed and how many TOC entries would be restored before writing anything.
- That dry-run preview now includes per-doc path, intended doc id, intended slug, and title when the snapshot markdown carries those values.
- Pass `--skip-docs` to restore only the TOC, or `--skip-toc` to restore only the docs.
- The snapshot restore is markdown-level recovery, not a byte-for-byte restore of original non-markdown Yuque formats.
- If you intentionally want to restore into a different repo, pass `--repo <namespace>/<repo>` together with `--allow-repo-override`.

## Recommended Workflow

1. Run `pull-dir-markdown` or otherwise verify the local directory is a complete mirror.
2. Review `yuque-index.json` and front matter so each file maps to the intended doc.
3. Run `sync-dir-toc` or `push-dir-markdown --sync-toc`.
4. Keep the automatic snapshot unless an equivalent backup already exists outside the skill.
5. If the TOC rewrite goes wrong, use `restore-repo-snapshot` against the captured snapshot directory.

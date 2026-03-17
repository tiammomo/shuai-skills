---
name: yuque-openapi
description: Cross-platform workflow for syncing local Markdown files or whole Markdown directories with Yuque knowledge bases and exporting Yuque documents back to local Markdown through the Yuque OpenAPI. Use when Codex needs to push generated `.md` files into Yuque, recursively sync a local markdown directory into a repo, pull Yuque docs or a full repo back to local markdown, build an incremental sync manifest from `yuque-index.json` or front matter, discover spaces/repos/slugs, or automate related repo and doc operations across personal and group spaces without assuming a Windows-only shell.
---

# Yuque OpenAPI

Use the bundled Python CLI for repeatable Yuque sync workflows. It uses only the Python standard library, so it works on Windows, macOS, and Linux anywhere `python` is available.

## Safety First

- Prefer `YUQUE_TOKEN` or `YUQUE_ACCESS_TOKEN` in the environment.
- Accept `--token` only when environment variables are not practical.
- Treat any user-shared token as sensitive. Do not echo it back, commit it, or place it in frontend code.
- If a token appears in chat or logs, advise rotation before further automation.
- Require explicit user confirmation for destructive delete operations.
- Treat TOC rewrites as source-of-truth operations. Keep the automatic snapshot enabled unless an equivalent backup already exists.

## Task Router

- Discover spaces, repos, docs, or basic CRUD behavior:
  Read [references/repo-doc-crud.md](./references/repo-doc-crud.md).
- Sync one markdown file to or from Yuque:
  Use `push-markdown` or `pull-markdown`, then read [references/repo-doc-crud.md](./references/repo-doc-crud.md) if payload or lookup rules matter.
- Sync a whole markdown directory with a repo:
  Start with `plan-dir-markdown`; add `--include-diff` when the review output should also show truncated unified diffs for divergent local vs remote markdown bodies, then read [references/dir-sync.md](./references/dir-sync.md).
- Rebuild only the remote hierarchy or TOC:
  Use `sync-dir-toc` or `push-dir-markdown --sync-toc`, then read [references/toc-sync.md](./references/toc-sync.md).
- Restore a repo from an automatic snapshot:
  Use `restore-repo-snapshot`, then read [references/toc-sync.md](./references/toc-sync.md).
- Run repeatable multi-repo jobs:
  Use `run-manifest`, then read [references/manifest.md](./references/manifest.md).
- Validate a manifest before execution:
  Use `validate-manifest`, then read [references/manifest.md](./references/manifest.md).
- Diagnose sync failures or surprising behavior:
  Read [references/troubleshooting.md](./references/troubleshooting.md).
- Work against a newly documented or unsupported endpoint:
  Read [references/endpoints.md](./references/endpoints.md) and fall back to `raw <METHOD> <PATH>`.

## Default Workflow

1. Verify access with `python scripts/yuque_api.py me`.
2. Discover spaces with `list-spaces --owner me` or `list-groups --owner me`.
3. Discover targets with `list-repos --owner me` or `list-repos --owner <login> --owner-type auto`.
4. Choose the smallest safe sync:
   `push-markdown` for one file, `plan-dir-markdown` for a directory, `sync-dir-toc` for hierarchy only.
5. Before TOC rewrites, pull the full repo or otherwise confirm the local tree is complete.
6. For batch work, persist a manifest and execute it with `run-manifest`.

## Reference Files

- [references/endpoints.md](./references/endpoints.md): reference index and command-family routing.
- [references/repo-doc-crud.md](./references/repo-doc-crud.md): space discovery, repo/doc CRUD, payload shapes, file-level markdown sync.
- [references/dir-sync.md](./references/dir-sync.md): directory sync planning, path rules, conflict rules, review previews, and `yuque-index.json`.
- [references/toc-sync.md](./references/toc-sync.md): TOC markdown shape, prune guard, and automatic snapshot behavior.
- [references/manifest.md](./references/manifest.md): manifest schema, batch execution rules, and output patterns.
- [references/troubleshooting.md](./references/troubleshooting.md): common failure modes, prune guard behavior, and recovery guidance.

## Bundled Resources

- `scripts/yuque_api.py`: stable cross-platform CLI entrypoint.
- `scripts/selftest_yuque_api.py`: offline regression checks for planning, diff previews, manifest execution, TOC sync, and backup protections.
- `scripts/check_yuque_skill.py`: one-click local check runner for selftests, skill validation, and CLI help smoke tests. It exits non-zero on failures, so it is ready to wire into CI.
- `scripts/yuque_api_lib/`: implementation modules for the CLI. Read only when patching or debugging the skill itself.
- `assets/manifests/`: starter manifest templates for common pull, push, and export workflows.

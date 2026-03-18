# Yuque OpenAPI Reference Index

## Contents

- [Reference Map](#reference-map)
- [Core Rules](#core-rules)
- [Official Docs](#official-docs)
- [Command Families](#command-families)
- [Escalation Rules](#escalation-rules)

Use this file as the routing page for the bundled references. Read only the task-specific file you need.

## Reference Map

| Task | Read this file |
| --- | --- |
| Discover spaces, repos, docs, or CRUD payloads | [repo-doc-crud.md](./repo-doc-crud.md) |
| Plan or run markdown directory sync | [dir-sync.md](./dir-sync.md) |
| Rebuild a remote TOC from a local tree or restore from a snapshot | [toc-sync.md](./toc-sync.md) |
| Run batch jobs, validate manifests, or inspect manifest shape | [manifest.md](./manifest.md) |
| Diagnose failed syncs or confusing behavior | [troubleshooting.md](./troubleshooting.md) |

## Core Rules

- Base URL: `https://www.yuque.com/api/v2`
- Auth header: `X-Auth-Token: <token>`
- Prefer `YUQUE_TOKEN` or `YUQUE_ACCESS_TOKEN`
- Treat TOC rewrites as source-of-truth operations
- Keep the automatic snapshot enabled before TOC updates unless an equivalent backup already exists

## Official Docs

- [Yuque Developer Overview](https://www.yuque.com/yuque/developer)
- [Yuque Developer API](https://www.yuque.com/yuque/developer/api)
- [Yuque OpenAPI](https://www.yuque.com/yuque/developer/openapi)

## Command Families

| Command family | Primary reference |
| --- | --- |
| `me`, `list-*`, `create-repo`, `update-repo`, `create-doc`, `update-doc`, `delete-*`, `raw` | [repo-doc-crud.md](./repo-doc-crud.md) |
| `push-markdown`, `pull-markdown`, `export-repo-markdown` | [repo-doc-crud.md](./repo-doc-crud.md) |
| `push-dir-markdown`, `pull-dir-markdown`, `plan-dir-markdown` | [dir-sync.md](./dir-sync.md) |
| `sync-dir-toc`, `push-dir-markdown --sync-toc`, `restore-repo-snapshot` | [toc-sync.md](./toc-sync.md) |
| `validate-manifest`, `run-manifest` | [manifest.md](./manifest.md) |
| Investigate common failures or mismatches | [troubleshooting.md](./troubleshooting.md) |

## Escalation Rules

- If the task is "just sync one file", start with `push-markdown` or `pull-markdown`.
- If the task is "keep a local directory aligned with a repo", start with `plan-dir-markdown`.
- If the task is "only fix hierarchy", use `sync-dir-toc` instead of rewriting doc bodies.
- If the task spans multiple repos, write or review a manifest before bulk execution.

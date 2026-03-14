# Repo And Doc Workflows

## Contents

- [Core Rules](#core-rules)
- [Repo Reference Conventions](#repo-reference-conventions)
- [Command To Endpoint Map](#command-to-endpoint-map)
- [Repo Payload Pattern](#repo-payload-pattern)
- [Doc Payload Pattern](#doc-payload-pattern)
- [Markdown File Sync](#markdown-file-sync)
- [Practical Notes](#practical-notes)

## Core Rules

- Base URL: `https://www.yuque.com/api/v2`
- Auth header: `X-Auth-Token: <token>`
- Prefer `YUQUE_TOKEN` or `YUQUE_ACCESS_TOKEN`
- Prefer `format=markdown` unless the task explicitly needs `html`, `lake`, or `asl`

## Repo Reference Conventions

- Repo refs can be either `<namespace>/<repo-slug>` or `<repo-id>`.
- Doc refs can be either a numeric id or a slug.
- Prefer `<namespace>/<repo-slug>` for reviewable automation and manifests.

## Command To Endpoint Map

| CLI command | HTTP method | Endpoint |
| --- | --- | --- |
| `me` | `GET` | `/user` |
| `list-groups --owner <login-or-id>` | `GET` | `/users/{user-id}/groups` after resolving the user |
| `list-spaces --owner <login-or-id>` | mixed | convenience aggregation of `/users/{owner}` or `/user` plus `/users/{user-id}/groups` |
| `list-repos --owner <login> --owner-type user` | `GET` | `/users/{login}/repos` |
| `list-repos --owner <login> --owner-type group` | `GET` | `/groups/{login}/repos` |
| `create-repo --owner <login> --owner-type user` | `POST` | `/users/{login}/repos` |
| `create-repo --owner <login> --owner-type group` | `POST` | `/groups/{login}/repos` |
| `get-repo <repo-ref>` | `GET` | `/repos/{repo}` or `/repos/{namespace}/{repo}` |
| `update-repo <repo-ref>` | `PUT` | `/repos/{repo}` or `/repos/{namespace}/{repo}` |
| `delete-repo <repo-ref> --yes` | `DELETE` | `/repos/{repo}` or `/repos/{namespace}/{repo}` |
| `list-docs <repo-ref>` | `GET` | `/repos/{repo}/docs` or `/repos/{namespace}/{repo}/docs` |
| `get-doc <repo-ref> <doc-ref>` | `GET` | `/repos/{repo}/docs/{doc}` or `/repos/{namespace}/{repo}/docs/{doc}` |
| `create-doc <repo-ref>` | `POST` | `/repos/{repo}/docs` or `/repos/{namespace}/{repo}/docs` |
| `update-doc <repo-ref> <doc-ref>` | `PUT` | `/repos/{repo}/docs/{doc}` or `/repos/{namespace}/{repo}/docs/{doc}` |
| `upsert-doc <repo-ref>` | mixed | `GET` existing doc, then `PUT` or `POST` |
| `delete-doc <repo-ref> <doc-ref> --yes` | `DELETE` | `/repos/{repo}/docs/{doc}` or `/repos/{namespace}/{repo}/docs/{doc}` |
| `raw <METHOD> <PATH>` | any | any path relative to the configured base URL |

## Repo Payload Pattern

Create or update repos with `name` and `slug`, plus optional metadata:

```json
{
  "name": "AI Delivery Playbook",
  "slug": "ai-delivery-playbook",
  "description": "Shared delivery standards",
  "public": 0
}
```

## Doc Payload Pattern

Use `format=markdown` by default:

```json
{
  "title": "Weekly Sync",
  "slug": "weekly-sync",
  "public": 1,
  "format": "markdown",
  "body": "# Weekly Sync\n\n- Item 1\n- Item 2"
}
```

Use `body_asl` for `lake` or `asl` formats:

```json
{
  "title": "Structured Doc",
  "slug": "structured-doc",
  "format": "lake",
  "body_asl": "<!doctype lake><p>Hello Yuque</p>"
}
```

## Markdown File Sync

- `push-markdown` reads a local UTF-8 markdown file, strips leading YAML front matter by default, derives the title from `--title` or the first `# H1`, then uploads with `format=markdown` and `body`.
- `push-markdown` prefers `yuque_doc_id`, then `yuque_doc_slug`, from front matter for stable round-trip updates.
- `push-markdown --lookup-by id` prevents a numeric lookup key from being reused as a created doc slug.
- `pull-markdown` fetches one doc detail response and writes the returned `body` field to a local `.md` file.
- `pull-markdown --front-matter` prefixes a YAML block with repo/doc ids, slug, title, visibility, and timestamps.
- `export-repo-markdown` fetches every doc detail response and writes one markdown file per doc plus a JSON index.
- `export-repo-markdown` can still use the `body` field even when Yuque reports a non-markdown format.

## Practical Notes

- `list-groups` first resolves the user to a numeric id, then requests `/users/{id}/groups`.
- `list-spaces` returns one synthetic `user` row plus zero or more `group` rows.
- `list-repos --owner me` resolves the current user first, then calls the user repos endpoint.
- `list-repos --owner-type auto` tries the user endpoint first, then the group endpoint on `404`.
- `upsert-doc --lookup-by id` avoids reusing a numeric lookup value as the created doc slug.
- Prefer body files over inline multi-paragraph shell arguments to avoid quoting issues across shells.
- Use `--extra-json` to pass fields not modeled by the CLI yet.
- Use `raw` when testing a newly documented Yuque endpoint before deciding whether the CLI should grow.

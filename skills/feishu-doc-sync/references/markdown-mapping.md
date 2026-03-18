# Markdown Mapping

## Contents

- [Recommended Feishu Pipeline](#recommended-feishu-pipeline)
- [Current Live-Validated Subset](#current-live-validated-subset)
- [Current Mapping Rules](#current-mapping-rules)
- [Current Feishu Pipeline Behavior](#current-feishu-pipeline-behavior)
- [Known Lossy Areas](#known-lossy-areas)
- [Table Handling](#table-handling)
- [Images And Attachments](#images-and-attachments)
- [Pull Strategy](#pull-strategy)
- [Example Assets](#example-assets)
- [Source Of Truth Recommendation](#source-of-truth-recommendation)
- [Official Sources](#official-sources)

## Recommended Feishu Pipeline

The current tenant-mode write path follows the official Feishu docx sequence:

1. Create the target docx document if it does not already exist.
2. Convert Markdown into Feishu document blocks.
3. Insert the returned blocks into the target document.

The official convert API points to the same create-document and descendant-block workflows that the current CLI uses.

## Current Live-Validated Subset

These parts are already covered by local smoke checks and tenant-mode live probes in this repository:

- front matter stripping by default for file-based writes
- UTF-8 BOM handling for Markdown files
- title inference from front matter, H1, or file stem
- headings
- normal paragraphs
- simple list blocks
- append flow with `append-markdown`
- destructive body replacement with `replace-markdown --confirm-replace`
- single-file push with `push-markdown`
- directory push with `push-dir`
- `--upload-media` backfill for standalone local Markdown image or attachment lines during append, replace, single-file push, and directory push
- single-file low-fidelity export with `pull-markdown --fidelity low`
- single-file higher-fidelity export for common blocks with `pull-markdown --fidelity high`
- directory low-fidelity export with `pull-dir --fidelity low`
- directory higher-fidelity export for common blocks with `pull-dir --fidelity high`
- explicit document media upload with `upload-media`
- `feishu-index.json` write-back after a successful push

Treat this list as the supported baseline for productionizing tenant-mode sync.

## Current Mapping Rules

The current CLI resolves metadata in this order:

1. front matter
2. `feishu-index.json`
3. local file content

Recognized front matter aliases:

- `title` or `feishu_title`
- `feishu_doc_token` or `doc_token`
- `feishu_folder_token` or `folder_token`
- `feishu_wiki_node_token` or `wiki_node_token`
- `feishu_sync_direction` or `sync_direction`

Default title behavior:

- use `title` from front matter if present
- else use the first H1
- else derive from the filename

Default content behavior:

- strip YAML front matter unless `--keep-front-matter` is set
- treat an empty post-processed body as a hard error

## Current Feishu Pipeline Behavior

`append-markdown`:

- converts Markdown to blocks
- with `--upload-media`, uploads standalone local Markdown image or attachment lines first and inserts them as Feishu image or file blocks
- appends those blocks under the selected parent block
- does not clear existing content

`replace-markdown`:

- lists the root page block
- deletes the existing root children
- with `--upload-media`, uploads standalone local Markdown image or attachment lines first and inserts them as Feishu image or file blocks
- appends the converted Markdown blocks as the new body

`push-markdown`:

- resolves mapping from front matter and `feishu-index.json`
- creates a new doc if no `doc_token` exists
- otherwise requires `--confirm-replace` and overwrites the existing doc body
- can use `--upload-media` to turn standalone local Markdown image or attachment lines into uploaded Feishu image or file blocks before writing
- updates `feishu-index.json` after a successful write

`push-dir`:

- runs `push-markdown` for every Markdown file under the root
- skips files marked `sync_direction: pull` unless overridden
- can reuse `--upload-media` for each file so standalone local Markdown image or attachment lines are uploaded into the destination doc workflow
- writes or updates one shared `feishu-index.json`

## Known Lossy Areas

Treat these as best-effort or not-yet-validated until the live implementation proves otherwise:

- task lists
- tables with complex merges
- inline image references inside paragraph text
- inline attachment links inside paragraph text
- non-standalone local media references that need richer Markdown rewriting than `--upload-media` currently performs
- block quotes with higher-fidelity nesting expectations
- custom admonition syntax
- footnotes
- definition lists
- raw HTML outside the supported convert subset
- Mermaid or other embedded diagram syntaxes
- reference-style links that rely on Markdown-only formatting behavior

## Table Handling

The official convert workflow documents one important caveat:

- when table blocks are converted and then inserted through the nested-block API, remove `merge_info` before insertion because that field is read-only

The current CLI already strips that field before descendant block creation.

## Images And Attachments

The official media upload API supports docx-specific upload points:

- `parent_type=docx_image` for images
- `parent_type=docx_file` for attachments

Use the target document token as `parent_node`.

The upload API documentation also notes:

- uploaded media is attached to the destination doc workflow, not shown as a normal Drive file
- `docs:document.media:upload` is the narrow scope for doc-media upload

This repository now implements an explicit live media-upload path in `feishu_doc_sync.py` through `upload-media`.

Current boundary:

- uploaded media can be pushed to a doc workflow and returns a `file_token`
- `append-markdown`, `replace-markdown`, `push-markdown`, and `push-dir` can now backfill standalone local Markdown image or attachment lines when `--upload-media` is enabled
- the first media-backfill version intentionally focuses on standalone Markdown lines, not inline links or raw HTML asset references

## Pull Strategy

Two pull strategies are worth separating:

- `raw_content` for quick plain-text export
- block-tree reconstruction for higher-fidelity Markdown regeneration

Use `raw_content` as the low-fidelity fallback. It is simpler, but it does not preserve all Markdown structure.

The current high-fidelity exporter is strongest for:

- headings
- paragraphs with common inline styles
- bullet and ordered lists
- quotes
- code blocks
- todo items
- simple callouts with nested text children
- simple tables without advanced merge semantics
- image and file placeholders that preserve Feishu tokens

Treat embeds, complex merged tables, and other unsupported blocks as review-required output until the exporter coverage expands.

## Example Assets

Reusable examples live under [../assets/examples/](../assets/examples/):

- [../assets/examples/feishu-index.minimal.json](../assets/examples/feishu-index.minimal.json)
- [../assets/examples/sample-sync-root/feishu-index.json](../assets/examples/sample-sync-root/feishu-index.json)
- [../assets/examples/sample-sync-root/new-doc.md](../assets/examples/sample-sync-root/new-doc.md)
- [../assets/examples/sample-sync-root/existing-doc.md](../assets/examples/sample-sync-root/existing-doc.md)

These files show the current expected index shape and front matter keys for tenant-mode push jobs.

## Source Of Truth Recommendation

For the current live version, prefer one-way source of truth per job:

- local Markdown is source of truth for push jobs
- remote docx is source of truth for pull jobs

Avoid automatic bidirectional merge until the block-to-Markdown exporter is mature.

## Official Sources

- [Convert Markdown or HTML to blocks](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/convert?lang=zh-CN)
- [Create document](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/create?lang=zh-CN)
- [Create blocks](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block-children/create?lang=zh-CN)
- [Upload media](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/media/upload_all)

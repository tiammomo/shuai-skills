# Manifest And Batch Workflows

## Contents

- [When To Use](#when-to-use)
- [Manifest Shape](#manifest-shape)
- [Generation Pattern](#generation-pattern)
- [Execution Rules](#execution-rules)
- [Output Patterns](#output-patterns)

## When To Use

- Use `run-manifest` for repeatable multi-repo operations.
- Use `validate-manifest` when you want a schema-like check before execution.
- Use `plan-dir-markdown --write-manifest` when you want a review step before executing sync actions.
- Use `raw` only when the CLI does not yet model the exact API call you need.

## Manifest Shape

`run-manifest` accepts either a JSON array of operations or an object with `operations`, `requests`, or `items`:

```json
{
  "continue_on_error": true,
  "operations": [
    {
      "command": "push-dir-markdown",
      "repo": "pearfl/tools",
      "source_dir": "./docs/tools"
    },
    {
      "command": "pull-dir-markdown",
      "repo": "pearfl/tools",
      "output_dir": "./exports/tools"
    }
  ]
}
```

## Generation Pattern

- `plan-dir-markdown --write-manifest sync-plan.json` writes an object with an `operations` array.
- Review that plan before executing it with `run-manifest sync-plan.json`.
- Run `validate-manifest sync-plan.json` when you want a fast structural check without touching Yuque.
- Prefer manifests over hand-written shell loops when the batch spans multiple repos or mixed operation types.
- Starter templates live under `assets/manifests/` for common pull, push+TOC, and multi-repo export flows.

## Execution Rules

- Each manifest operation must be a JSON object with a `command` field.
- `validate-manifest` checks for unsupported fields, required arguments, and invalid choices before execution.
- `continue_on_error` can live either on the CLI flag or inside the manifest root object.
- `run-manifest` executes operations in order and returns one result item per operation.
- For destructive operations, keep the explicit confirmation flag in the manifest itself, such as `--yes`-equivalent fields.

## Output Patterns

- `--select kind,login,name --output table list-spaces --owner me` gives a compact discovery view.
- `--select name --output text` emits one projected field per line.
- `--select name,slug,public --output table` is useful for reviewing repos or docs.
- `--output jsonl` emits one JSON object per line for downstream scripts.
- Plain `json` without `--select` preserves the original API wrapper and metadata.

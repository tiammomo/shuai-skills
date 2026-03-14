from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from .client import YuqueClient
from .command_types import CommandSpec, OperationDispatcher
from .core import YuqueApiError, emit_progress, maybe_json

OperationValidator = Callable[[Dict[str, Any]], Any]


def handle_raw(client: YuqueClient, args: argparse.Namespace) -> Any:
    query = maybe_json(args.query_json, field_name="--query-json")
    payload = maybe_json(args.data_json, field_name="--data-json") if args.data_json is not None else None
    return client.request(args.method, args.path, query=query, payload=payload)


def load_manifest(path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8-sig")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise YuqueApiError(f"Manifest must be valid JSON: {exc}") from exc

    metadata: Dict[str, Any] = {}
    operations: Any = parsed
    if isinstance(parsed, dict):
        metadata = {key: value for key, value in parsed.items() if key not in {"operations", "requests", "items"}}
        for key in ("operations", "requests", "items"):
            if key in parsed:
                operations = parsed[key]
                break

    if not isinstance(operations, list):
        raise YuqueApiError("Manifest must be a JSON array or an object with operations/requests/items.")
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise YuqueApiError(f"Manifest operation #{index + 1} must be a JSON object.")
    return operations, metadata


def validate_manifest_operations(
    operations: List[Dict[str, Any]],
    *,
    validate_operation: OperationValidator,
) -> List[Dict[str, Any]]:
    validated: List[Dict[str, Any]] = []
    total = len(operations)
    for index, operation in enumerate(operations, start=1):
        command_name = str(operation.get("command") or "<missing>")
        emit_progress(f"[manifest validate {index}/{total}] {command_name}")
        namespace = validate_operation(operation)
        validated.append(
            {
                "index": index,
                "command": command_name,
                "ok": True,
                "normalized": vars(namespace),
            }
        )
    return validated


def handle_validate_manifest(args: argparse.Namespace, *, validate_operation: OperationValidator) -> Any:
    operations, metadata = load_manifest(args.manifest)
    validated = validate_manifest_operations(
        operations,
        validate_operation=validate_operation,
    )
    return {
        "data": validated,
        "meta": {
            "count": len(validated),
            "continue_on_error": bool(metadata.get("continue_on_error")),
            "manifest": args.manifest,
            "valid": True,
        },
    }


def handle_run_manifest(
    client: YuqueClient,
    args: argparse.Namespace,
    *,
    dispatch_operation: OperationDispatcher,
    validate_operation: OperationValidator,
) -> Any:
    operations, metadata = load_manifest(args.manifest)
    validate_manifest_operations(operations, validate_operation=validate_operation)
    continue_on_error = bool(args.continue_on_error or metadata.get("continue_on_error"))
    results = []
    failures = 0
    total = len(operations)
    for index, operation in enumerate(operations, start=1):
        command_name = str(operation.get("command") or "<missing>")
        emit_progress(f"[manifest {index}/{total}] starting {command_name}")
        try:
            result = dispatch_operation(client, operation)
            results.append(
                {
                    "index": index,
                    "command": command_name,
                    "ok": True,
                    "result": result,
                }
            )
            emit_progress(f"[manifest {index}/{total}] ok={index - failures} failed={failures} command={command_name}")
        except YuqueApiError as exc:
            failures += 1
            error_result = {
                "index": index,
                "command": command_name,
                "ok": False,
                "error": {
                    "message": str(exc),
                    "status": exc.status,
                    "method": exc.method,
                    "path": exc.path,
                    "payload": exc.payload,
                },
            }
            if not continue_on_error:
                raise YuqueApiError(
                    f"Manifest operation #{index} failed: {exc}",
                    status=exc.status,
                    payload=error_result,
                    method=exc.method,
                    path=exc.path,
                ) from exc
            results.append(error_result)
            emit_progress(f"[manifest {index}/{total}] ok={index - failures} failed={failures} command={command_name}")
    return {
        "data": results,
        "meta": {
            "count": len(results),
            "failed": failures,
            "continue_on_error": continue_on_error,
        },
    }


def configure_raw(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("method", help="HTTP method such as GET, POST, PUT, DELETE.")
    parser.add_argument("path", help="Path under /api/v2, such as /user or repos/foo/bar/docs.")
    parser.add_argument("--query-json", help="Optional JSON object merged into the query string.")
    parser.add_argument("--data-json", help="Optional JSON request body.")


def configure_run_manifest(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("manifest", help="Path to a JSON manifest file, or '-' for stdin.")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue running later operations after an error.")


def configure_validate_manifest(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("manifest", help="Path to a JSON manifest file, or '-' for stdin.")


def build_utility_command_specs(dispatch_operation: OperationDispatcher, validate_operation: OperationValidator) -> Tuple[CommandSpec, ...]:
    return (
        CommandSpec("raw", "Send a raw Yuque API request.", handle_raw, configure_raw, {"query_json": None, "data_json": None}),
        CommandSpec("validate-manifest", "Validate a JSON manifest without executing it.", lambda _client, args: handle_validate_manifest(args, validate_operation=validate_operation), configure_validate_manifest, {}),
        CommandSpec("run-manifest", "Run a JSON manifest of Yuque CLI operations.", lambda client, args: handle_run_manifest(client, args, dispatch_operation=dispatch_operation, validate_operation=validate_operation), configure_run_manifest, {"continue_on_error": False}),
    )

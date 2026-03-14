from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Iterable, List

from .client import YuqueClient
from .command_types import CommandSpec
from .core import (
    DEFAULT_BASE_URL,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_RETRY_MAX_BACKOFF,
    DEFAULT_TIMEOUT,
    YuqueApiError,
)
from .doc_commands import DOC_COMMAND_SPECS
from .space_repo_commands import SPACE_REPO_COMMAND_SPECS
from .sync_commands import build_sync_command_specs
from .utility_commands import build_utility_command_specs, load_manifest


def _dispatch_operation(client: YuqueClient, operation: Dict[str, Any]) -> Any:
    return perform_command(client, namespace_from_operation(operation))


class _ManifestValidationParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise YuqueApiError(message)


def command_spec(name: str) -> CommandSpec:
    try:
        return COMMAND_REGISTRY[name]
    except KeyError as exc:
        raise YuqueApiError(f"Unsupported command: {name}") from exc


def build_command_parser(spec: CommandSpec) -> argparse.ArgumentParser:
    parser = _ManifestValidationParser(prog=spec.name, add_help=False, allow_abbrev=False)
    if spec.configure is not None:
        spec.configure(parser)
    return parser


def _iter_action_values(value: Any) -> Iterable[str]:
    if isinstance(value, (list, tuple)):
        for item in value:
            yield str(item)
        return
    yield str(value)


def operation_to_argv(operation: Dict[str, Any]) -> List[str]:
    command = operation.get("command")
    if not isinstance(command, str):
        raise YuqueApiError("Manifest command must be a string.")
    spec = command_spec(command)
    parser = build_command_parser(spec)
    actions = [action for action in parser._actions if action.dest != "help"]
    allowed_fields = {"command", *(action.dest for action in actions)}
    unknown_fields = sorted(key for key in operation if key not in allowed_fields)
    if unknown_fields:
        raise YuqueApiError(
            f"Manifest command '{command}' contains unsupported fields: {', '.join(unknown_fields)}."
        )

    argv: List[str] = []
    positional_actions = [action for action in actions if not action.option_strings]
    optional_actions = [action for action in actions if action.option_strings]

    for action in positional_actions:
        if action.dest not in operation:
            continue
        value = operation[action.dest]
        if value is None:
            continue
        argv.extend(_iter_action_values(value))

    for action in optional_actions:
        if action.dest not in operation:
            continue
        value = operation[action.dest]
        if isinstance(action, argparse._StoreTrueAction):
            if bool(value):
                argv.append(action.option_strings[0])
            continue
        if isinstance(action, argparse._StoreFalseAction):
            if value is False:
                argv.append(action.option_strings[0])
            continue
        if value is None:
            continue
        argv.append(action.option_strings[0])
        argv.extend(_iter_action_values(value))
    return argv


def validate_operation(operation: Dict[str, Any]) -> argparse.Namespace:
    command = operation.get("command")
    if not isinstance(command, str):
        raise YuqueApiError("Manifest command must be a string.")
    spec = command_spec(command)
    parser = build_command_parser(spec)
    argv = operation_to_argv(operation)
    return parser.parse_args(argv)


COMMAND_SPECS = (
    *SPACE_REPO_COMMAND_SPECS,
    *DOC_COMMAND_SPECS,
    *build_sync_command_specs(_dispatch_operation),
    *build_utility_command_specs(_dispatch_operation, validate_operation),
)

COMMAND_REGISTRY = {spec.name: spec for spec in COMMAND_SPECS}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cross-platform Yuque OpenAPI helper.")
    parser.add_argument("--token", help="Yuque personal access token. Prefer YUQUE_TOKEN or YUQUE_ACCESS_TOKEN.")
    parser.add_argument("--base-url", default=os.environ.get("YUQUE_BASE_URL", DEFAULT_BASE_URL), help=f"Yuque API base URL. Defaults to {DEFAULT_BASE_URL}.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Request timeout in seconds. Defaults to {DEFAULT_TIMEOUT}.")
    parser.add_argument("--retries", type=int, default=int(os.environ.get("YUQUE_RETRIES", DEFAULT_RETRIES)), help=f"Retries for 429 and 5xx responses. Defaults to {DEFAULT_RETRIES}.")
    parser.add_argument("--retry-backoff", type=float, default=float(os.environ.get("YUQUE_RETRY_BACKOFF", DEFAULT_RETRY_BACKOFF)), help=f"Initial retry backoff in seconds. Defaults to {DEFAULT_RETRY_BACKOFF}.")
    parser.add_argument("--retry-max-backoff", type=float, default=float(os.environ.get("YUQUE_RETRY_MAX_BACKOFF", DEFAULT_RETRY_MAX_BACKOFF)), help=f"Maximum retry backoff in seconds. Defaults to {DEFAULT_RETRY_MAX_BACKOFF}.")
    parser.add_argument("--output", choices=("json", "jsonl", "table", "text"), default="json", help="Output format. Defaults to json.")
    parser.add_argument("--select", help="Comma-separated field paths to project from response data, such as name,slug,user.login.")

    subparsers = parser.add_subparsers(dest="command", required=True)
    for spec in COMMAND_SPECS:
        subparser = subparsers.add_parser(spec.name, help=spec.help)
        if spec.configure is not None:
            spec.configure(subparser)
    return parser


def namespace_from_operation(operation: Dict[str, Any]) -> argparse.Namespace:
    if "command" not in operation:
        raise YuqueApiError("Each manifest operation requires a command field.")
    command = operation["command"]
    if not isinstance(command, str):
        raise YuqueApiError("Manifest command must be a string.")
    validate_operation(operation)
    spec = command_spec(command)
    values: Dict[str, Any] = {"command": command}
    values.update(spec.defaults)
    values.update(operation)
    return argparse.Namespace(**values)


def perform_command(client: YuqueClient, args: argparse.Namespace) -> Any:
    return command_spec(args.command).handler(client, args)


__all__ = [
    "COMMAND_REGISTRY",
    "COMMAND_SPECS",
    "CommandSpec",
    "build_parser",
    "build_command_parser",
    "command_spec",
    "load_manifest",
    "namespace_from_operation",
    "operation_to_argv",
    "perform_command",
    "validate_operation",
]

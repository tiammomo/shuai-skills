from __future__ import annotations

import argparse
from typing import Any, Dict

from .core import DEFAULT_LIMIT, YuqueApiError, choose_body_field, maybe_json, read_body


def add_paging_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Page size.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Automatically request pages until exhausted.",
    )


def add_repo_write_arguments(
    parser: argparse.ArgumentParser,
    *,
    name_required: bool,
    slug_required: bool,
) -> None:
    parser.add_argument("--name", required=name_required, help="Repo name.")
    parser.add_argument("--slug", required=slug_required, help="Repo slug.")
    parser.add_argument("--description", help="Repo description.")
    parser.add_argument(
        "--public",
        type=int,
        choices=(0, 1),
        help="Repo visibility flag expected by Yuque.",
    )
    parser.add_argument(
        "--extra-json",
        help="Optional JSON object merged into the request payload.",
    )


def add_doc_write_arguments(parser: argparse.ArgumentParser, *, title_required: bool) -> None:
    parser.add_argument("--title", required=title_required, help="Document title.")
    parser.add_argument("--slug", help="Document slug.")
    parser.add_argument(
        "--public",
        type=int,
        choices=(0, 1),
        help="Public visibility flag expected by Yuque.",
    )
    parser.add_argument(
        "--format",
        default="markdown",
        choices=("markdown", "html", "lake", "asl"),
        help="Document body format. Defaults to markdown.",
    )
    parser.add_argument("--body", help="Inline document body.")
    parser.add_argument(
        "--body-file",
        help="Read the document body from a file. Use '-' for stdin.",
    )
    parser.add_argument(
        "--body-field",
        choices=("auto", "body", "body_asl"),
        default="auto",
        help="Override the body field name. Defaults to auto.",
    )
    parser.add_argument(
        "--extra-json",
        help="Optional JSON object merged into the request payload.",
    )


def configure_owner_lookup(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--owner", required=True, help="Owner login, numeric id, or 'me'.")


def configure_repo_only(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo", help="Repo ref: <repo-id> or <namespace>/<repo-slug>.")


def configure_get_doc(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    parser.add_argument("doc", help="Doc slug or id.")


def build_doc_payload(args: argparse.Namespace, *, require_title: bool) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if getattr(args, "title", None) is not None:
        payload["title"] = args.title
    elif require_title:
        raise YuqueApiError("--title is required.")

    if getattr(args, "slug", None):
        payload["slug"] = args.slug
    if getattr(args, "public", None) is not None:
        payload["public"] = args.public
    if getattr(args, "format", None):
        payload["format"] = args.format

    body = read_body(getattr(args, "body", None), getattr(args, "body_file", None))
    if body is not None:
        payload[choose_body_field(args.format, args.body_field)] = body

    extra = maybe_json(getattr(args, "extra_json", None), field_name="--extra-json")
    payload.update(extra)
    return payload


def build_repo_payload(args: argparse.Namespace, *, require_name: bool, require_slug: bool) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if getattr(args, "name", None) is not None:
        payload["name"] = args.name
    elif require_name:
        raise YuqueApiError("--name is required.")

    if getattr(args, "slug", None) is not None:
        payload["slug"] = args.slug
    elif require_slug:
        raise YuqueApiError("--slug is required.")

    if getattr(args, "description", None) is not None:
        payload["description"] = args.description
    if getattr(args, "public", None) is not None:
        payload["public"] = args.public

    extra = maybe_json(getattr(args, "extra_json", None), field_name="--extra-json")
    payload.update(extra)
    return payload

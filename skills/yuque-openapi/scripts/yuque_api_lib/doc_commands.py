from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .client import YuqueClient, build_path, build_repo_path, fetch_all_pages
from .command_builders import add_doc_write_arguments, add_paging_arguments, build_doc_payload, configure_get_doc, configure_repo_only
from .command_types import CommandSpec
from .core import DEFAULT_INDEX_FILE, DEFAULT_LIMIT, YuqueApiError
from .markdown_docs import export_repo_markdown_bundle, pull_doc_to_markdown, push_markdown_file, should_reuse_doc_lookup_as_slug


def handle_list_docs(client: YuqueClient, args: argparse.Namespace) -> Any:
    path = build_repo_path(args.repo) + build_path("docs")
    if args.all:
        return fetch_all_pages(
            lambda offset, limit: client.request(
                "GET",
                path,
                query={"offset": offset, "limit": limit},
            ),
            offset=args.offset,
            limit=args.limit,
        )
    return client.request(
        "GET",
        path,
        query={"offset": args.offset, "limit": args.limit},
    )


def handle_get_doc(client: YuqueClient, args: argparse.Namespace) -> Any:
    return client.request("GET", build_repo_path(args.repo) + build_path("docs", args.doc))


def handle_pull_markdown(client: YuqueClient, args: argparse.Namespace) -> Any:
    return {
        "data": pull_doc_to_markdown(
            client,
            repo_ref=args.repo,
            doc_ref=args.doc,
            output_path=Path(args.output),
            front_matter=args.front_matter,
        )
    }


def handle_export_repo_markdown(client: YuqueClient, args: argparse.Namespace) -> Any:
    result = export_repo_markdown_bundle(
        client,
        repo_ref=args.repo,
        export_dir=Path(args.output_dir),
        front_matter=args.front_matter,
        index_file=args.index_file,
        name_by=args.name_by,
    )
    return {
        "data": {
            "repo": result["repo"],
            "output_dir": result["output_dir"],
            "index_file": result["index_file"],
            "count": result["count"],
        }
    }


def handle_create_doc(client: YuqueClient, args: argparse.Namespace) -> Any:
    payload = build_doc_payload(args, require_title=True)
    return client.request(
        "POST",
        build_repo_path(args.repo) + build_path("docs"),
        payload=payload,
    )


def handle_update_doc(client: YuqueClient, args: argparse.Namespace) -> Any:
    payload = build_doc_payload(args, require_title=False)
    if not payload:
        raise YuqueApiError("Nothing to update. Provide at least one writable field.")
    return client.request(
        "PUT",
        build_repo_path(args.repo) + build_path("docs", args.doc),
        payload=payload,
    )


def handle_upsert_doc(client: YuqueClient, args: argparse.Namespace) -> Any:
    payload = build_doc_payload(args, require_title=True)
    path = build_repo_path(args.repo) + build_path("docs", args.doc)
    try:
        client.request("GET", path)
    except YuqueApiError as exc:
        if exc.status == 404:
            if "slug" not in payload and should_reuse_doc_lookup_as_slug(args.doc, args.lookup_by):
                payload["slug"] = args.doc
            return client.request(
                "POST",
                build_repo_path(args.repo) + build_path("docs"),
                payload=payload,
            )
        raise
    return client.request("PUT", path, payload=payload)


def handle_push_markdown(client: YuqueClient, args: argparse.Namespace) -> Any:
    return {
        "data": push_markdown_file(
            client,
            repo_ref=args.repo,
            source_path=Path(args.source),
            doc_ref=args.doc,
            title=args.title,
            slug=args.slug,
            public=args.public,
            lookup_by=args.lookup_by,
            keep_front_matter=args.keep_front_matter,
            extra_json=args.extra_json,
        )
    }


def handle_delete_doc(client: YuqueClient, args: argparse.Namespace) -> Any:
    if not args.yes:
        raise YuqueApiError("delete-doc is destructive. Re-run with --yes.")
    return client.request(
        "DELETE",
        build_repo_path(args.repo) + build_path("docs", args.doc),
    )


def configure_list_docs(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    add_paging_arguments(parser)


def configure_pull_markdown(parser: argparse.ArgumentParser) -> None:
    configure_get_doc(parser)
    parser.add_argument("output", help="Output markdown file path.")
    parser.add_argument("--front-matter", action="store_true", help="Prefix the local markdown file with doc metadata front matter.")


def configure_export_repo_markdown(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    parser.add_argument("output_dir", help="Directory to write markdown files into.")
    parser.add_argument("--front-matter", action="store_true", help="Prefix each markdown file with doc metadata front matter.")
    parser.add_argument("--index-file", default=DEFAULT_INDEX_FILE, help=f"Name of the metadata index file written into the export directory. Defaults to {DEFAULT_INDEX_FILE}.")
    parser.add_argument("--name-by", choices=("slug", "title", "id"), default="slug", help="How to name exported markdown files. Defaults to slug.")


def configure_create_doc(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    add_doc_write_arguments(parser, title_required=True)


def configure_update_doc(parser: argparse.ArgumentParser) -> None:
    configure_get_doc(parser)
    add_doc_write_arguments(parser, title_required=False)


def configure_upsert_doc(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    parser.add_argument("--doc", required=True, help="Existing doc slug or id to look up before updating.")
    parser.add_argument("--lookup-by", choices=("auto", "slug", "id"), default="auto", help="How to treat --doc when deciding whether it is safe to reuse as slug.")
    add_doc_write_arguments(parser, title_required=True)


def configure_push_markdown(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    parser.add_argument("source", help="Local markdown file path.")
    parser.add_argument("--doc", help="Existing Yuque doc slug or id to look up before updating. Defaults to slug or file stem.")
    parser.add_argument("--title", help="Doc title. Defaults to first markdown H1 or file stem.")
    parser.add_argument("--slug", help="Doc slug for creation. Defaults to --doc or file stem when safe.")
    parser.add_argument("--public", type=int, choices=(0, 1), help="Default public visibility for creation when local metadata does not specify one.")
    parser.add_argument("--lookup-by", choices=("auto", "slug", "id"), default="auto", help="How to treat --doc when deciding whether it is safe to reuse as slug.")
    parser.add_argument("--keep-front-matter", action="store_true", help="Keep YAML front matter in the uploaded body instead of stripping it.")
    parser.add_argument("--extra-json", help="Optional JSON object merged into the request payload.")


def configure_delete_doc(parser: argparse.ArgumentParser) -> None:
    configure_get_doc(parser)
    parser.add_argument("--yes", action="store_true", help="Confirm deletion. Required for destructive calls.")


DOC_COMMAND_SPECS = (
    CommandSpec("list-docs", "List docs in a repo.", handle_list_docs, configure_list_docs, {"offset": 0, "limit": DEFAULT_LIMIT, "all": False}),
    CommandSpec("get-doc", "Fetch a doc by slug or id.", handle_get_doc, configure_get_doc, {}),
    CommandSpec("pull-markdown", "Download one Yuque doc to a local markdown file.", handle_pull_markdown, configure_pull_markdown, {"front_matter": False}),
    CommandSpec("export-repo-markdown", "Export every doc in a repo to local markdown files.", handle_export_repo_markdown, configure_export_repo_markdown, {"front_matter": False, "index_file": DEFAULT_INDEX_FILE, "name_by": "slug"}),
    CommandSpec("create-doc", "Create a doc in a repo.", handle_create_doc, configure_create_doc, {"title": None, "slug": None, "public": None, "format": "markdown", "body": None, "body_file": None, "body_field": "auto", "extra_json": None}),
    CommandSpec("update-doc", "Update an existing doc.", handle_update_doc, configure_update_doc, {"title": None, "slug": None, "public": None, "format": "markdown", "body": None, "body_file": None, "body_field": "auto", "extra_json": None}),
    CommandSpec("upsert-doc", "Create a doc when missing, otherwise update it.", handle_upsert_doc, configure_upsert_doc, {"title": None, "slug": None, "public": None, "format": "markdown", "body": None, "body_file": None, "body_field": "auto", "extra_json": None, "lookup_by": "auto"}),
    CommandSpec("push-markdown", "Sync one local markdown file into a Yuque doc.", handle_push_markdown, configure_push_markdown, {"doc": None, "title": None, "slug": None, "public": None, "lookup_by": "auto", "keep_front_matter": False, "extra_json": None}),
    CommandSpec("delete-doc", "Delete a doc. Destructive.", handle_delete_doc, configure_delete_doc, {"yes": False}),
)

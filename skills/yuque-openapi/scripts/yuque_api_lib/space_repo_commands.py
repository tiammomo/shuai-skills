from __future__ import annotations

import argparse
from typing import Any, Dict, List

from .client import YuqueClient, build_repo_path, fetch_all_pages, request_owner_repo_collection, resolve_user, unwrap_data
from .command_builders import add_paging_arguments, add_repo_write_arguments, build_repo_payload, configure_owner_lookup, configure_repo_only
from .command_types import CommandSpec
from .core import DEFAULT_LIMIT, YuqueApiError


def handle_me(client: YuqueClient, _: argparse.Namespace) -> Any:
    return client.request("GET", "/user")


def handle_list_groups(client: YuqueClient, args: argparse.Namespace) -> Any:
    user = resolve_user(client, args.owner)
    return client.request("GET", f"/users/{user['id']}/groups")


def handle_list_spaces(client: YuqueClient, args: argparse.Namespace) -> Any:
    user = resolve_user(client, args.owner)
    groups_response = client.request("GET", f"/users/{user['id']}/groups")
    groups = unwrap_data(groups_response)
    if not isinstance(groups, list):
        raise YuqueApiError("Expected group list while building spaces.")

    spaces: List[Dict[str, Any]] = [
        {
            "kind": "user",
            "id": user.get("id"),
            "login": user.get("login"),
            "name": user.get("name"),
            "namespace": user.get("login"),
            "type": user.get("type"),
            "public": user.get("public"),
        }
    ]
    for group in groups:
        if not isinstance(group, dict):
            continue
        spaces.append(
            {
                "kind": "group",
                "id": group.get("id"),
                "login": group.get("login"),
                "name": group.get("name"),
                "namespace": group.get("login"),
                "type": group.get("type"),
                "public": group.get("public"),
            }
        )
    return {
        "data": spaces,
        "meta": {
            "count": len(spaces),
            "groups_count": len(groups),
            "owner": user.get("login"),
        },
    }


def handle_list_repos(client: YuqueClient, args: argparse.Namespace) -> Any:
    if args.all:
        return fetch_all_pages(
            lambda offset, limit: request_owner_repo_collection(
                client,
                owner=args.owner,
                owner_type=args.owner_type,
                method="GET",
                query={"offset": offset, "limit": limit},
            ),
            offset=args.offset,
            limit=args.limit,
        )
    return request_owner_repo_collection(
        client,
        owner=args.owner,
        owner_type=args.owner_type,
        method="GET",
        query={"offset": args.offset, "limit": args.limit},
    )


def handle_create_repo(client: YuqueClient, args: argparse.Namespace) -> Any:
    payload = build_repo_payload(args, require_name=True, require_slug=True)
    return request_owner_repo_collection(
        client,
        owner=args.owner,
        owner_type=args.owner_type,
        method="POST",
        payload=payload,
    )


def handle_get_repo(client: YuqueClient, args: argparse.Namespace) -> Any:
    return client.request("GET", build_repo_path(args.repo))


def handle_update_repo(client: YuqueClient, args: argparse.Namespace) -> Any:
    payload = build_repo_payload(args, require_name=False, require_slug=False)
    if not payload:
        raise YuqueApiError("Nothing to update. Provide at least one writable field.")
    return client.request("PUT", build_repo_path(args.repo), payload=payload)


def handle_delete_repo(client: YuqueClient, args: argparse.Namespace) -> Any:
    if not args.yes:
        raise YuqueApiError("delete-repo is destructive. Re-run with --yes.")
    return client.request("DELETE", build_repo_path(args.repo))


def configure_list_repos(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--owner", required=True, help="Owner login. Use 'me' for the current user.")
    parser.add_argument(
        "--owner-type",
        choices=("auto", "user", "group"),
        default="auto",
        help="Owner namespace type. 'auto' tries user first, then group on 404.",
    )
    add_paging_arguments(parser)


def configure_create_repo(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--owner", required=True, help="Owner login. Use 'me' for the current user.")
    parser.add_argument(
        "--owner-type",
        choices=("auto", "user", "group"),
        default="auto",
        help="Owner namespace type. 'auto' tries user first, then group on 404.",
    )
    add_repo_write_arguments(parser, name_required=True, slug_required=True)


def configure_update_repo(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    add_repo_write_arguments(parser, name_required=False, slug_required=False)


def configure_delete_repo(parser: argparse.ArgumentParser) -> None:
    configure_repo_only(parser)
    parser.add_argument("--yes", action="store_true", help="Confirm deletion. Required for destructive calls.")


SPACE_REPO_COMMAND_SPECS = (
    CommandSpec("me", "Fetch the current user.", handle_me, defaults={}),
    CommandSpec("list-repos", "List repos for a user or group.", handle_list_repos, configure_list_repos, {"owner_type": "auto", "offset": 0, "limit": DEFAULT_LIMIT, "all": False}),
    CommandSpec("list-groups", "List groups for a user. Uses the user's numeric id under the hood.", handle_list_groups, configure_owner_lookup, {}),
    CommandSpec("list-spaces", "List the personal space plus any group spaces for a user.", handle_list_spaces, configure_owner_lookup, {}),
    CommandSpec("create-repo", "Create a repo for a user or group.", handle_create_repo, configure_create_repo, {"owner_type": "auto", "description": None, "public": None, "extra_json": None}),
    CommandSpec("get-repo", "Fetch a repo by id or namespace/repo.", handle_get_repo, configure_repo_only, {}),
    CommandSpec("update-repo", "Update a repo.", handle_update_repo, configure_update_repo, {"name": None, "slug": None, "description": None, "public": None, "extra_json": None}),
    CommandSpec("delete-repo", "Delete a repo. Destructive.", handle_delete_repo, configure_delete_repo, {"yes": False}),
)

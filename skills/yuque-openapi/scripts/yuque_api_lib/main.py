from __future__ import annotations

from .client import YuqueClient, get_token
from .commands import build_parser, perform_command
from .core import YuqueApiError
from .output import emit_error, emit_result


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        token = get_token(args.token)
        client = YuqueClient(
            token=token,
            base_url=args.base_url,
            timeout=args.timeout,
            retries=args.retries,
            retry_backoff=args.retry_backoff,
            retry_max_backoff=args.retry_max_backoff,
        )
        result = perform_command(client, args)
        emit_result(result, output=args.output, select=args.select)
        return 0
    except YuqueApiError as exc:
        return emit_error(exc)

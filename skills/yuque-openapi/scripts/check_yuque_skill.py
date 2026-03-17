#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
YUQUE_API = SCRIPT_DIR / "yuque_api.py"
SELFTEST = SCRIPT_DIR / "selftest_yuque_api.py"


def default_validator_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    return codex_home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"


def resolve_validator_path(raw_path: str) -> Path:
    return Path(raw_path).expanduser().resolve()


def run_step(label: str, command: List[str]) -> None:
    print(f"==> {label}")
    completed = subprocess.run(
        command,
        cwd=str(SKILL_DIR),
        text=True,
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n", file=sys.stderr)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline checks for the Yuque OpenAPI skill.")
    parser.add_argument("--validator", default=str(default_validator_path()), help="Path to skill-creator quick_validate.py.")
    parser.add_argument("--skip-selftest", action="store_true", help="Skip the offline Yuque self-tests.")
    parser.add_argument("--skip-validate", action="store_true", help="Skip skill-creator validation.")
    parser.add_argument("--skip-help-smoke", action="store_true", help="Skip CLI --help smoke tests.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not args.skip_selftest:
        run_step("Offline self-tests", [sys.executable, str(SELFTEST)])

    if not args.skip_validate:
        validator_path = resolve_validator_path(args.validator)
        if not validator_path.exists():
            raise SystemExit(f"Validator script not found: {validator_path}. Pass --validator or --skip-validate.")
        run_step("Skill validation", [sys.executable, str(validator_path), str(SKILL_DIR)])

    if not args.skip_help_smoke:
        help_commands = [
            ("CLI help", [sys.executable, str(YUQUE_API), "--help"]),
            ("Directory plan help", [sys.executable, str(YUQUE_API), "plan-dir-markdown", "--help"]),
            ("Manifest validate help", [sys.executable, str(YUQUE_API), "validate-manifest", "--help"]),
            ("Manifest help", [sys.executable, str(YUQUE_API), "run-manifest", "--help"]),
            ("Directory push help", [sys.executable, str(YUQUE_API), "push-dir-markdown", "--help"]),
            ("Snapshot restore help", [sys.executable, str(YUQUE_API), "restore-repo-snapshot", "--help"]),
        ]
        for label, command in help_commands:
            run_step(label, command)

    print("All Yuque skill checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

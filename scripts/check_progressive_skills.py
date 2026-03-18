#!/usr/bin/env python3
"""Validate progressive-skill conventions for this repository."""

from __future__ import annotations

import re
import sys
from collections import deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
SECONDARY_HEADING_RE = re.compile(r"^## (.+?)\s*$")
CONTENTS_LINK_RE = re.compile(r"\[[^\]]+\]\(#([^)]+)\)")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REQUIRED_HEADINGS = (
    "## Task Router",
    "## Progressive Loading",
    "## Default Workflow",
)
REFERENCE_TOC_LINE_THRESHOLD = 100
MAX_REFERENCE_HOPS = 2


def parse_frontmatter(text: str) -> dict[str, str] | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    fields: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            return None
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def has_nonempty_dir(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def slugify_heading(heading: str) -> str:
    slug = heading.strip().lower().replace("`", "")
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"\s", "-", slug)
    return slug.strip("-")


def extract_secondary_headings(lines: list[str]) -> list[tuple[str, int]]:
    headings: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        match = SECONDARY_HEADING_RE.match(line)
        if match:
            headings.append((match.group(1).strip(), index))
    return headings


def extract_contents_slugs(lines: list[str], headings: list[tuple[str, int]], contents_index: int) -> set[str]:
    start = headings[contents_index][1] + 1
    if contents_index + 1 < len(headings):
        end = headings[contents_index + 1][1]
    else:
        end = len(lines)

    slugs: set[str] = set()
    for line in lines[start:end]:
        for match in CONTENTS_LINK_RE.finditer(line):
            slugs.add(match.group(1).strip().lower())
    return slugs


def extract_reference_targets(source_file: Path, skill_dir: Path) -> tuple[set[Path], list[str]]:
    targets: set[Path] = set()
    errors: list[str] = []
    skill_root = skill_dir.resolve()
    text = source_file.read_text(encoding="utf-8")

    for match in MARKDOWN_LINK_RE.finditer(text):
        raw_target = match.group(1).strip()
        if not raw_target:
            continue
        target_token = raw_target.split()[0].strip("<>")
        if not target_token or target_token.startswith("#"):
            continue
        if "://" in target_token or target_token.startswith(("mailto:", "data:")):
            continue

        path_part = target_token.split("#", 1)[0]
        if not path_part:
            continue

        resolved = (source_file.parent / Path(path_part)).resolve()
        try:
            relative_target = resolved.relative_to(skill_root)
        except ValueError:
            continue

        if resolved.suffix.lower() != ".md":
            continue
        if not relative_target.parts or relative_target.parts[0] != "references":
            continue
        if not resolved.is_file():
            source_label = source_file.relative_to(skill_root).as_posix()
            errors.append(
                f"{skill_dir.name}:{source_label} links to missing reference '{relative_target.as_posix()}'"
            )
            continue
        targets.add(resolved)

    return targets, errors


def validate_reference_reachability(skill_dir: Path, skill_md: Path, reference_files: list[Path]) -> list[str]:
    errors: list[str] = []
    graph: dict[Path, set[Path]] = {}

    skill_targets, skill_errors = extract_reference_targets(skill_md, skill_dir)
    graph[skill_md.resolve()] = skill_targets
    errors.extend(skill_errors)

    for reference_file in reference_files:
        targets, target_errors = extract_reference_targets(reference_file, skill_dir)
        graph[reference_file.resolve()] = targets
        errors.extend(target_errors)

    depths: dict[Path, int] = {}
    queue: deque[tuple[Path, int]] = deque((target, 1) for target in graph.get(skill_md.resolve(), set()))
    while queue:
        current, depth = queue.popleft()
        previous_depth = depths.get(current)
        if previous_depth is not None and previous_depth <= depth:
            continue
        depths[current] = depth
        for neighbor in graph.get(current, set()):
            queue.append((neighbor, depth + 1))

    for reference_file in reference_files:
        resolved = reference_file.resolve()
        reference_label = f"{skill_dir.name}:{reference_file.name}"
        if resolved not in depths:
            errors.append(
                f"{reference_label}: reference file is unreachable from SKILL.md; link it directly or from a directly linked routing reference"
            )
            continue
        if depths[resolved] > MAX_REFERENCE_HOPS:
            errors.append(
                f"{reference_label}: reference file is only reachable after {depths[resolved]} hops; keep reference routing within {MAX_REFERENCE_HOPS} hops from SKILL.md"
            )

    return errors


def validate_reference_file(skill_dir: Path, reference_file: Path) -> list[str]:
    errors: list[str] = []
    lines = reference_file.read_text(encoding="utf-8").splitlines()
    headings = extract_secondary_headings(lines)
    if not headings:
        return errors

    contents_index = next((i for i, (heading, _) in enumerate(headings) if heading == "Contents"), None)
    long_reference = len(lines) > REFERENCE_TOC_LINE_THRESHOLD
    reference_label = f"{skill_dir.name}:{reference_file.name}"

    if long_reference and contents_index is None:
        errors.append(
            f"{reference_label}: reference files over {REFERENCE_TOC_LINE_THRESHOLD} lines should start with a '## Contents' section"
        )
        return errors

    if contents_index is None:
        return errors

    if headings[0][0] != "Contents":
        errors.append(f"{reference_label}: '## Contents' should be the first secondary heading for easier reference routing")

    target_headings = [heading for heading, _ in headings if heading != "Contents"]
    if not target_headings:
        errors.append(f"{reference_label}: '## Contents' should point to at least one task-specific section")
        return errors

    contents_slugs = extract_contents_slugs(lines, headings, contents_index)
    missing_headings = [heading for heading in target_headings if slugify_heading(heading) not in contents_slugs]
    if missing_headings:
        errors.append(
            f"{reference_label}: '## Contents' is missing links for {', '.join(repr(heading) for heading in missing_headings)}"
        )

    return errors


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir.name}: missing SKILL.md"]

    text = skill_md.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    if line_count > 500:
        errors.append(f"{skill_dir.name}: SKILL.md has {line_count} lines; keep it under 500 for progressive loading")

    frontmatter = parse_frontmatter(text)
    if frontmatter is None:
        errors.append(f"{skill_dir.name}: SKILL.md is missing valid YAML frontmatter")
    else:
        expected_keys = {"name", "description"}
        actual_keys = set(frontmatter)
        if actual_keys != expected_keys:
            errors.append(
                f"{skill_dir.name}: frontmatter keys must be exactly {sorted(expected_keys)}, found {sorted(actual_keys)}"
            )
        if frontmatter.get("name") != skill_dir.name:
            errors.append(f"{skill_dir.name}: frontmatter name must match directory name")
        description = frontmatter.get("description", "")
        if "Use when" not in description:
            errors.append(f"{skill_dir.name}: description should include an explicit 'Use when ...' trigger clause")

    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"{skill_dir.name}: missing required section '{heading}'")

    references_dir = skill_dir / "references"
    scripts_dir = skill_dir / "scripts"
    assets_dir = skill_dir / "assets"

    if has_nonempty_dir(references_dir):
        reference_files = sorted(references_dir.glob("*.md"))
        if "## Reference Files" not in text:
            errors.append(f"{skill_dir.name}: skills with references/ should expose a '## Reference Files' section")
        if "references/" not in text:
            errors.append(f"{skill_dir.name}: SKILL.md should route to at least one references/ file")
        for reference_file in reference_files:
            errors.extend(validate_reference_file(skill_dir, reference_file))
        errors.extend(validate_reference_reachability(skill_dir, skill_md, reference_files))

    if has_nonempty_dir(scripts_dir) and "scripts/" not in text:
        errors.append(f"{skill_dir.name}: SKILL.md should mention bundled scripts/ when scripts are present")

    if any(has_nonempty_dir(path) for path in (scripts_dir, references_dir, assets_dir)):
        if "## Bundled Resources" not in text:
            errors.append(f"{skill_dir.name}: skills with bundled resources should include a '## Bundled Resources' section")

    progressive_hints = (
        "Read only",
        "Load only",
        "Do not preload",
    )
    if not any(hint in text for hint in progressive_hints):
        errors.append(f"{skill_dir.name}: '## Progressive Loading' should explain how to load references on demand")

    return errors


def main() -> int:
    skill_dirs = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
    all_errors: list[str] = []
    for skill_dir in skill_dirs:
        all_errors.extend(validate_skill(skill_dir))

    if all_errors:
        for error in all_errors:
            print(f"ERROR: {error}")
        return 1

    print(f"Progressive skill validation passed for {len(skill_dirs)} skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

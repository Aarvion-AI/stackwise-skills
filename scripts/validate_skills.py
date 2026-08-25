#!/usr/bin/env python3
"""Validate every skill in skills/ against the Stackwise template contract.

Checks structure, frontmatter, verification loops, and reference integrity.
Exit code 0 = all skills pass; 1 = failures (printed per skill).
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO / "skills"

REQUIRED_FRONTMATTER = ["name", "description", "license"]
REQUIRED_METADATA = ["version", "category", "frameworks", "triggers"]
VALID_CATEGORIES = {"core", "frontend", "backend", "mobile", "infra", "qa"}
REQUIRED_SECTIONS = [
    "## When to Use This Skill",
    "## Core Workflow",
    "## Reference Guide",
    "## Key Patterns",
    "## Common Mistakes",
]
MAX_BODY_LINES = 250


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"\A---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m:
        return {}, text
    fm: dict = {}
    current_dict = None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if line.startswith("  ") and current_dict is not None:
            k, _, v = line.strip().partition(":")
            fm[current_dict][k.strip()] = v.strip().strip('"')
        else:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip().strip('"')
            if v == "":
                fm[k] = {}
                current_dict = k
            else:
                fm[k] = v
                current_dict = None
    return fm, m.group(2)


def validate_skill(skill_dir: Path) -> list[str]:
    errors = []
    skill_md = skill_dir / "SKILL.md"
    refs_dir = skill_dir / "references"

    if not skill_md.exists():
        return [f"missing SKILL.md"]

    text = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    if not fm:
        errors.append("missing or malformed YAML frontmatter")
        return errors

    for key in REQUIRED_FRONTMATTER:
        if key not in fm or not fm[key]:
            errors.append(f"frontmatter missing '{key}'")

    if fm.get("name") != skill_dir.name:
        errors.append(
            f"frontmatter name '{fm.get('name')}' != directory name '{skill_dir.name}'"
        )

    desc = fm.get("description", "")
    if isinstance(desc, str) and not desc.startswith("Use when"):
        errors.append("description must start with 'Use when' (drives auto-loading)")

    meta = fm.get("metadata")
    if not isinstance(meta, dict):
        errors.append("frontmatter missing 'metadata' block")
    else:
        for key in REQUIRED_METADATA:
            if key not in meta or not meta[key]:
                errors.append(f"metadata missing '{key}'")
        if meta.get("category") and meta["category"] not in VALID_CATEGORIES:
            errors.append(
                f"metadata.category '{meta['category']}' not in {sorted(VALID_CATEGORIES)}"
            )

    for section in REQUIRED_SECTIONS:
        if section not in body:
            errors.append(f"missing required section '{section}'")

    body_lines = len(body.splitlines())
    if body_lines > MAX_BODY_LINES:
        errors.append(
            f"SKILL.md body is {body_lines} lines (max {MAX_BODY_LINES}); move depth to references/"
        )

    workflow = re.search(r"## Core Workflow\n(.*?)(?=\n## )", body, re.DOTALL)
    if workflow and not re.search(
        r"(until clean|until (it |they |all )?pass|fix.*re-?run|re-?run until)",
        workflow.group(1),
        re.IGNORECASE,
    ):
        errors.append(
            "Core Workflow has no verification loop "
            "(needs an explicit 'fix and re-run until clean/passing' step)"
        )

    listed_refs = set(re.findall(r"`references/([\w./-]+\.md)`", body))
    actual_refs = (
        {p.name for p in refs_dir.glob("*.md")} if refs_dir.is_dir() else set()
    )
    if not actual_refs:
        errors.append("references/ is missing or empty (need 3-6 reference files)")
    for ref in listed_refs - actual_refs:
        errors.append(f"Reference Guide lists references/{ref} but file does not exist")
    for ref in actual_refs - listed_refs:
        errors.append(f"references/{ref} exists but is not in the Reference Guide table")

    for ref in sorted(actual_refs):
        n = len((refs_dir / ref).read_text(encoding="utf-8").splitlines())
        if n < 40:
            errors.append(f"references/{ref} is only {n} lines; too thin to earn a file")

    all_files = [skill_md] + (sorted(refs_dir.glob("*.md")) if refs_dir.is_dir() else [])
    for f in all_files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "—" in line:
                errors.append(
                    f"{f.relative_to(skill_dir)}:{i} contains an em dash; use a hyphen, comma, or period (repo rule: no em dashes)"
                )

    return errors


def main() -> int:
    if not SKILLS_DIR.is_dir():
        print("ERROR: skills/ directory not found")
        return 1

    skill_dirs = sorted(d for d in SKILLS_DIR.iterdir() if d.is_dir())
    if not skill_dirs:
        print("ERROR: no skills found in skills/")
        return 1

    failed = 0
    for skill_dir in skill_dirs:
        errors = validate_skill(skill_dir)
        if errors:
            failed += 1
            print(f"\nFAIL {skill_dir.name}")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"PASS {skill_dir.name}")

    print(f"\n{len(skill_dirs) - failed}/{len(skill_dirs)} skills pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

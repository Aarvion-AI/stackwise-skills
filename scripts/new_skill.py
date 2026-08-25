#!/usr/bin/env python3
"""Scaffold a new skill from templates/SKILL_TEMPLATE.md.

Creates skills/<name>-expert/ with a SKILL.md pre-filled from the answers you
give and empty reference stubs, so a contributor starts from a structure the
validator already understands.

    python3 scripts/new_skill.py svelte --category frontend \
        --frameworks "Svelte 5, SvelteKit 2" \
        --refs runes-reactivity load-functions forms-actions testing
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "templates" / "SKILL_TEMPLATE.md"
SKILLS_DIR = REPO / "skills"

CATEGORIES = ["frontend", "backend", "mobile", "infra", "qa", "core"]
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

REFERENCE_STUB = """# {title}

<!-- 100-300 lines, code-heavy, current framework version, no filler prose.
     Show the pattern, then the failure it prevents. Delete this comment. -->

## <Pattern>

```
<runnable example>
```

<Why this shape and not the obvious alternative.>
"""


def slugify(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", raw.strip().lower()).strip("-")


def titleize(slug: str) -> str:
    return " ".join(word.capitalize() for word in slug.split("-"))


def build_skill_md(name: str, args: argparse.Namespace, refs: list[str]) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace("<framework>-expert", name)
    text = text.replace("<Framework> Expert", f"{titleize(args.framework)} Expert")
    text = text.replace(
        "category: <frontend | backend | mobile | infra | qa>",
        f"category: {args.category}",
    )
    if args.frameworks:
        text = text.replace(
            'frameworks: <Framework + versions covered, e.g. "React 19, Next.js 15">',
            f'frameworks: "{args.frameworks}"',
        )

    rows = "\n".join(
        f"| <Topic> | `references/{ref}.md` | <trigger condition> |" for ref in refs
    )
    text = re.sub(
        r"\| <Topic> \| `references/<file>\.md` \| <trigger condition> \|\n"
        r"\| <Topic> \| `references/<file>\.md` \| <trigger condition> \|",
        rows,
        text,
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("framework", help="Framework slug, e.g. 'svelte' or 'spring-boot'")
    parser.add_argument("--category", choices=CATEGORIES, required=True)
    parser.add_argument("--frameworks", default="", help='Versions covered, e.g. "Svelte 5, SvelteKit 2"')
    parser.add_argument(
        "--refs",
        nargs="+",
        default=["patterns", "architecture", "testing"],
        help="Reference file slugs to stub out (3-6 recommended)",
    )
    args = parser.parse_args()

    args.framework = slugify(args.framework)
    if not NAME_PATTERN.match(args.framework):
        print(f"ERROR: '{args.framework}' is not a valid slug (lowercase, hyphens, no version numbers)")
        return 1

    suffix = "-qa-expert" if args.category == "qa" else "-expert"
    name = args.framework + suffix
    skill_dir = SKILLS_DIR / name

    if skill_dir.exists():
        print(f"ERROR: {skill_dir.relative_to(REPO)} already exists")
        return 1
    if not 3 <= len(args.refs) <= 6:
        print(f"ERROR: pass 3-6 --refs (got {len(args.refs)})")
        return 1

    refs = [slugify(r) for r in args.refs]
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(build_skill_md(name, args, refs), encoding="utf-8")
    for ref in refs:
        (skill_dir / "references" / f"{ref}.md").write_text(
            REFERENCE_STUB.format(title=titleize(ref)), encoding="utf-8"
        )

    print(f"Created skills/{name}/")
    print(f"  SKILL.md")
    for ref in refs:
        print(f"  references/{ref}.md")
    print(
        "\nNext: fill in every <placeholder>, then run\n"
        "  python3 scripts/validate_skills.py\n"
        "It will fail until the stubs have real content. That is the point."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

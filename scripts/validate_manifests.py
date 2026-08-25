#!/usr/bin/env python3
"""Validate the Claude Code plugin and marketplace manifests.

Checks that both parse, that the plugin they describe matches the repo layout,
and that their versions agree. Exit code 0 = valid; 1 = failures.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / ".claude-plugin" / "plugin.json"
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"


def load(path: Path, errors: list[str]) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.relative_to(REPO)}: {exc}")
        return {}


def main() -> int:
    errors: list[str] = []
    plugin = load(PLUGIN, errors)
    marketplace = load(MARKETPLACE, errors)
    if errors:
        for e in errors:
            print(f"  - {e}")
        return 1

    for key in ("name", "version", "description", "license"):
        if not plugin.get(key):
            errors.append(f"plugin.json missing '{key}'")

    skills_dir = REPO / plugin.get("skills", "./skills/").lstrip("./")
    if not skills_dir.is_dir():
        errors.append(f"plugin.json skills path '{plugin.get('skills')}' does not exist")

    entries = marketplace.get("plugins") or []
    if not entries:
        errors.append("marketplace.json lists no plugins")

    for entry in entries:
        if entry.get("name") != plugin.get("name"):
            errors.append(
                f"marketplace plugin '{entry.get('name')}' does not match "
                f"plugin.json name '{plugin.get('name')}'"
            )
        if entry.get("version") != plugin.get("version"):
            errors.append(
                f"version mismatch: plugin.json {plugin.get('version')} vs "
                f"marketplace.json {entry.get('version')}"
            )

    if errors:
        print("FAIL plugin manifests")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"PASS plugin manifests (stackwise {plugin['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

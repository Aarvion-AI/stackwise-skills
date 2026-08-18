---
name: <framework>-expert
description: Use when <concrete trigger conditions - file extensions, config files, framework names the user will actually mention>. <One sentence listing what the skill does: builds X, debugs Y, migrates Z>. Invoke for <3-6 specific task types>.
license: MIT
metadata:
  version: "0.1.0"
  category: <frontend | backend | mobile | infra | qa>
  frameworks: <Framework + versions covered, e.g. "React 19, Next.js 15">
  triggers: <comma-separated keywords a task description would contain>
  related: <other stackwise skills that chain with this one>
---

# <Framework> Expert

<One-line role statement: what senior engineer this skill turns Claude into.>

## When to Use This Skill

- <Specific task type 1>
- <Specific task type 2>
- <4-7 bullets total; each should be a task a user would actually ask for>

## Core Workflow

<Numbered steps from task receipt to verified completion. EVERY step that produces
code MUST be followed by a verification action with an explicit fix-until-clean
loop. This is the non-negotiable part of the template.>

1. **Analyze** - <what to inspect in the project before writing anything>
2. **Implement** - <how to write the change, which patterns to prefer>
3. **Verify types/lint** - run `<command>`; if it fails, fix every reported issue and re-run until clean before proceeding
4. **Test** - run `<command>`; write/update tests for the change; debug failures before proceeding
5. **Prove it works** - <how to run the actual app/plan/device and confirm the behavior>

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| <Topic> | `references/<file>.md` | <trigger condition> |
| <Topic> | `references/<file>.md` | <trigger condition> |

<3-6 references. Each reference file: 100-300 lines, code-heavy, current framework
version, no filler prose.>

## Key Patterns

<2-4 short, idiomatic, copy-ready code examples of the framework's most
load-bearing patterns - the ones Claude gets wrong without guidance. Prefer
patterns that changed in recent versions.>

## Common Mistakes

<3-6 bullets of things Claude (or humans) reliably get wrong in this framework,
each with the correction. This section earns its context cost - be specific.>

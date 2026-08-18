# Contributing a Framework Skill

Adding a framework to Stackwise is one well-defined PR. CI validates the structure automatically, so if `scripts/validate_skills.py` passes locally, your PR is reviewable.

## Add a skill in 5 steps

1. **Claim it** - open an issue titled `skill: <framework>` so two people don't build the same one. Check the [README roadmap](README.md#roadmap--contribute-a-framework) for unclaimed frameworks.
2. **Copy the template** - `cp -r templates/SKILL_TEMPLATE.md skills/<framework>-expert/SKILL.md` and create `skills/<framework>-expert/references/`.
3. **Write the SKILL.md** - follow the template sections exactly. The hard requirements:
   - `description` frontmatter starts with **"Use when"** and names concrete triggers (file extensions, config files, framework keywords). This is what makes the skill auto-load - write it for the matcher, not for humans.
   - **Every Core Workflow step that produces code is followed by a verification step** with a fix-until-clean loop ("run X; fix all issues and re-run until clean"). Skills without verification loops are not accepted.
   - Body stays under ~200 lines. Depth goes in `references/`, not the SKILL.md.
4. **Write 3–6 reference files** - each 100–300 lines, code-heavy, targeting the **current major version** of the framework. Every reference must be listed in the SKILL.md Reference Guide table with a "Load When" condition.
5. **Validate and open the PR** - run `python3 scripts/validate_skills.py`, fix anything it reports, then open a PR. Add your skill's row to the README table and tick the roadmap checkbox.

## Quality bar

Every skill inherits the repo-wide rules in [skills/engineering-rules/SKILL.md](skills/engineering-rules/SKILL.md): reusable, maintainable, readable code; no AI slop; dead code removed on every touch; comments only for non-obvious "why" decisions; **no em dashes anywhere** (CI rejects them). Code samples inside your skill must themselves follow these rules.

- **Current versions only.** A React skill teaching class components or a Terraform skill on 0.x will be rejected. State the versions covered in `metadata.frameworks`.
- **Patterns Claude gets wrong.** The Key Patterns and Common Mistakes sections should target what models actually miss - recent API changes, footguns, deprecated idioms that dominate training data. "How to write a for loop" wastes context.
- **No marketing prose.** Every line either changes what Claude does or gets deleted in review.
- **Runnable commands.** Verification commands must be real (`tsc --noEmit`, `flutter analyze`, `terraform validate`), not placeholders.

## Updating an existing skill

Version bumps (framework released a new major) are the most valuable recurring contribution. Bump `metadata.version`, update the affected references, and note the framework version change in the PR title.

## Skill naming

`<framework>-expert` for implementation skills (`svelte-expert`), `<area>-qa-expert` pattern reserved for cross-cutting QA skills. Lowercase, hyphens, no version numbers in names.

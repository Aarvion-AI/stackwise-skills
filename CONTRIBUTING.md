# Contributing a Framework Skill

Adding a framework to Stackwise is one well-defined PR. CI validates the structure automatically, so if `scripts/validate_skills.py` passes locally, your PR is reviewable.

## Add a skill in 5 steps

1. **Claim it** - open an issue titled `skill: <framework>` so two people don't build the same one. Check the [README roadmap](README.md#roadmap--contribute-a-framework) for unclaimed frameworks.
2. **Copy the template** - `mkdir -p skills/<framework>-expert/references && cp templates/SKILL_TEMPLATE.md skills/<framework>-expert/SKILL.md`.
3. **Write the SKILL.md** - follow the template sections exactly. The hard requirements:
   - `description` frontmatter starts with **"Use when"** and names concrete triggers (file extensions, config files, framework keywords). This is what makes the skill auto-load - write it for the matcher, not for humans.
   - **Every Core Workflow step that produces code is followed by a verification step** with a fix-until-clean loop ("run X; fix all issues and re-run until clean"). Skills without verification loops are not accepted.
   - Body stays under ~200 lines. Depth goes in `references/`, not the SKILL.md.
4. **Write 3-6 reference files** - each 100-300 lines, code-heavy, targeting the **current major version** of the framework. Every reference must be listed in the SKILL.md Reference Guide table with a "Load When" condition.
5. **Try it, validate, open the PR** - load the skill in Claude Code (below), confirm it actually fires and gives good guidance, run `python3 scripts/validate_skills.py`, fix anything it reports, then open a PR. Add your skill's row to the README table and tick the roadmap checkbox.

## Run it locally before you open the PR

Point Claude Code at your checkout instead of the published marketplace:

```bash
git clone https://github.com/<you>/stackwise-skills && cd stackwise-skills
```

```
/plugin marketplace add ./
/plugin install stackwise@stackwise-skills
```

Then open a real project in that framework and ask for a task your skill should
handle. Two things to check, both of which reviewers will check too:

- **It fires on its own.** Do not invoke the skill by name. If it does not load
  from an ordinary request, the `description` is the problem, not the body.
  `/context` shows what loaded.
- **The guidance holds up.** Run the workflow end to end on real code. Every
  verification command in your Core Workflow must actually run in that project.

Re-run `/plugin marketplace update stackwise-skills` after editing to pick up
changes, and validate the structure before pushing:

```bash
python3 scripts/validate_skills.py   # no dependencies, Python 3.10+
```

CI runs exactly this on every PR, so a green local run means a green PR.

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

## Review and merge

PRs are reviewed by a maintainer, usually within a week. Expect review comments
on skill content: a skill that duplicates what models already do well gets
trimmed, not merged as-is. Keep the discussion in the PR so the reasoning stays
searchable for the next contributor.

CI must be green and the PR checklist filled before merge. We squash-merge, so
your local commit history does not need to be tidy, but the PR title does: it
becomes the changelog line. Add a `## Unreleased` entry to
[CHANGELOG.md](CHANGELOG.md) for anything that changes skill behavior.

## Licensing

Stackwise Skills is MIT licensed. By submitting a PR you agree that your
contribution is licensed under the same terms and that you have the right to
submit it. There is no CLA. If you are adapting material from elsewhere, make
sure its license permits redistribution under MIT and note the source in the PR.

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md). Report
security concerns privately per [SECURITY.md](SECURITY.md) rather than in a
public issue.

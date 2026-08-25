## What

<!-- New skill: which framework? | Update: which skill, what changed? -->
<!-- Link the issue this closes: Closes #123 -->

## Checklist (new or updated skill)

- [ ] `python3 scripts/validate_skills.py` passes locally
- [ ] `description` starts with "Use when" and names concrete triggers
- [ ] Every Core Workflow step that produces code has a fix-until-clean verification loop
- [ ] References target the framework's **current major version** (stated in `metadata.frameworks`)
- [ ] README table row added / roadmap checkbox ticked (new skills)
- [ ] Verification commands are real and runnable, not placeholders
- [ ] Loaded the plugin from a local checkout and confirmed the skill auto-loads on a real task, without naming it
- [ ] `CHANGELOG.md` Unreleased entry added (anything that changes skill behavior)
- [ ] No em dashes anywhere (CI rejects them)

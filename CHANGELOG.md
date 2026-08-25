# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html): a new skill
is a minor bump, guidance corrections are a patch, and a change to the skill
template contract or plugin layout is a major.

## [Unreleased]

### Added

- `scripts/new_skill.py` scaffolds a skill directory, a pre-filled `SKILL.md`,
  and reference stubs from the template.
- Contributor governance: Code of Conduct, security policy, support guide,
  CODEOWNERS, and structured issue forms.

### Changed

- `scripts/validate_skills.py` now rejects SKILL.md files that still contain
  template placeholders, matched verbatim against `templates/SKILL_TEMPLATE.md`
  so real angle brackets in code samples are not flagged.
- Manifest validation moved to `scripts/validate_manifests.py` and now checks
  that plugin and marketplace names and versions agree.

## [0.1.0] - 2026-08-18

### Added

- 14 skills across core, frontend, backend, mobile, infra, and QA:
  `engineering-rules`, `react-expert`, `vue-expert`, `nestjs-expert`,
  `fastapi-expert`, `fastify-expert`, `go-expert`, `flutter-expert`,
  `react-native-expert`, `swiftui-expert`, `jetpack-compose-expert`,
  `terraform-expert`, `playwright-expert`, `mobile-qa-expert`.
- `templates/SKILL_TEMPLATE.md` defining the skill contract: "Use when"
  description, verification loops in every Core Workflow step, and a
  Reference Guide table.
- `scripts/validate_skills.py` enforcing that contract, run on every PR by
  `.github/workflows/validate.yml`.
- Claude Code plugin and marketplace manifests under `.claude-plugin/`.

[Unreleased]: https://github.com/Aarvion-AI/stackwise-skills/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Aarvion-AI/stackwise-skills/releases/tag/v0.1.0

# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html): a new skill
is a minor bump, guidance corrections are a patch, and a change to the skill
template contract or plugin layout is a major.

## [Unreleased]

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

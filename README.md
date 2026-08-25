# Stackwise Skills

[![Validate skills](https://github.com/Aarvion-AI/stackwise-skills/actions/workflows/validate.yml/badge.svg)](https://github.com/Aarvion-AI/stackwise-skills/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Skills](https://img.shields.io/badge/skills-14-brightgreen.svg)](#whats-inside)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**End-to-end development skills for Claude Code - frontend, backend, mobile, infra, and QA - one plugin install.**

Every skill is framework-specific, production-focused, and follows one enforced template, so Claude loads exactly the expertise your stack needs and nothing else. Ship a new feature or fix a bug with the same pipeline across web, mobile, and infrastructure - including the step most skill packs skip: **verifying the change on a real browser or real device before you call it done.**

## Install

```
/plugin marketplace add Aarvion-AI/stackwise-skills
/plugin install stackwise@stackwise-skills
```

Skills activate automatically based on what you're working on - open a `.tsx` file and ask for a feature, and `react-expert` loads; touch a `main.tf`, and `terraform-expert` loads. No manual invocation needed.

## What's inside

| Category | Skill | Covers |
|---|---|---|
| Core | `engineering-rules` | Repo-wide code rules: reusability, readability, no AI slop, dead-code removal, why-only comments |
| Frontend | `react-expert` | React 19, Next.js App Router, Server Components, state management, performance |
| Frontend | `vue-expert` | Vue 3.5, Composition API, Nuxt 4, Pinia |
| Backend | `nestjs-expert` | NestJS 11, modules/DI, validation, TypeORM/Prisma, auth, testing |
| Backend | `fastapi-expert` | FastAPI, Pydantic v2, async SQLAlchemy, dependency injection, testing |
| Backend | `fastify-expert` | Fastify 5, plugins/encapsulation, TypeBox validation, hooks, testing |
| Backend | `go-expert` | Go 1.23+, net/http services, errors/context, concurrency, pgx/sqlc |
| Mobile | `flutter-expert` | Flutter 3.x, Riverpod/Bloc, GoRouter, platform channels |
| Mobile | `react-native-expert` | React Native 0.7x, Expo Router, native modules, platform handling |
| Mobile | `swiftui-expert` | iOS native: SwiftUI, Swift 6 concurrency, Observation, SwiftData |
| Mobile | `jetpack-compose-expert` | Android native: Compose, state/recomposition, Hilt, Navigation |
| Infra | `terraform-expert` | Terraform 1.x, module design, state management, plan review, CI |
| QA (web) | `playwright-expert` | Playwright E2E, fixtures, network mocking, visual regression, CI |
| QA (mobile) | `mobile-qa-expert` | Appium 2, real-device clouds (AWS Device Farm, BrowserStack), unattended flows |

Each skill is a folder: a lean `SKILL.md` (when to use, core workflow with verification loops, key patterns) plus `references/` files that load only when the task needs them - so 9 skills today or 50 tomorrow cost the same context.

## Why this exists

Most skill packs cover *writing* code. Real feature work is write → wire the API → migrate the schema → change the infra → **prove it works**. Stackwise skills bake verification into every workflow step: type-check until clean, run the test suite, drive the actual app. The mobile QA skill runs your change on a physical device in the cloud - the difference between "compiles" and "ships."

## Roadmap - contribute a framework

The skill template and CI validation make adding a framework a well-defined PR: claim it in an issue, copy [templates/SKILL_TEMPLATE.md](templates/SKILL_TEMPLATE.md), write 3-6 references, and run the validator. Full walkthrough in [CONTRIBUTING.md](CONTRIBUTING.md).

- [x] React · Vue · NestJS · FastAPI · Fastify · Go · Flutter · React Native · SwiftUI · Jetpack Compose · Terraform · Playwright · Appium
- [ ] Frontend: Angular, Svelte/SvelteKit, Astro
- [ ] Backend: Django, Spring Boot, Rails, Laravel, .NET, Elixir/Phoenix
- [ ] Mobile: Kotlin Multiplatform, native watchOS/Wear OS, mobile release engineering (Fastlane, store rollouts)
- [ ] Infra: AWS CDK, Pulumi, Kubernetes/Helm, GitHub Actions, Docker
- [ ] QA: Cypress, Maestro, Detox, k6 (load), pytest/Jest deep-dives
- [ ] Data: PostgreSQL, Redis, Kafka, dbt

## Contributing

New frameworks, version bumps on existing skills, and corrections to guidance
that has gone stale are all welcome. Start here:

- **[Good first issues](https://github.com/Aarvion-AI/stackwise-skills/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)** - unclaimed frameworks, scoped and ready to pick up
- [CONTRIBUTING.md](CONTRIBUTING.md) - the skill contract, how to run a skill
  from a local checkout, and the quality bar reviewers apply
- [Claim a framework](https://github.com/Aarvion-AI/stackwise-skills/issues/new?template=new-skill.yml)
  before you start, so two people do not write the same skill
- [Report stale guidance](https://github.com/Aarvion-AI/stackwise-skills/issues/new?template=skill-fix.yml)
  when a framework moves and a skill does not

Scaffolding is one command, and the validator tells you what is still missing:

```bash
python3 scripts/new_skill.py <framework> --category frontend --refs a b c
python3 scripts/validate_skills.py
```

Every PR runs the same validator, which enforces the template contract: a "Use when" description, a verification loop in the Core Workflow,
and every reference file listed in the Reference Guide table. Run it locally and
your PR is already green.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
Security concerns go through [SECURITY.md](SECURITY.md), not a public issue.

## License

MIT. See [LICENSE](LICENSE). Contributions are accepted under the same license.

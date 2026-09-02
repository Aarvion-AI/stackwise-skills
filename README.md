# Stackwise Skills

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
| Backend | `stripe-expert` | Stripe API, Payment Elements, Checkout, subscriptions, webhooks, billing |
| Infra | `github-actions-expert` | GitHub Actions, workflows, event triggers, secrets, matrix strategies, artifacts, observability |
| QA (web) | `cypress-expert` | Cypress E2E, query selectors, commands, network intercepts, fixtures, CI integration |
| QA (web) | `playwright-expert` | Playwright E2E, fixtures, network mocking, visual regression, CI |
| QA (mobile) | `mobile-qa-expert` | Appium 2, real-device clouds (AWS Device Farm, BrowserStack), unattended flows |

Each skill is a folder: a lean `SKILL.md` (when to use, core workflow with verification loops, key patterns) plus `references/` files that load only when the task needs them - so 9 skills today or 50 tomorrow cost the same context.

## Why this exists

Most skill packs cover *writing* code. Real feature work is write → wire the API → migrate the schema → change the infra → **prove it works**. Stackwise skills bake verification into every workflow step: type-check until clean, run the test suite, drive the actual app. The mobile QA skill runs your change on a physical device in the cloud - the difference between "compiles" and "ships."

## Roadmap - contribute a framework

The skill template and CI validation make adding a framework a well-defined PR. Pick an unclaimed one, copy [templates/SKILL_TEMPLATE.md](templates/SKILL_TEMPLATE.md), and see [CONTRIBUTING.md](CONTRIBUTING.md).

- [x] React · Vue · NestJS · FastAPI · Fastify · Go · Flutter · React Native · SwiftUI · Jetpack Compose · Terraform · Playwright · Appium
- [ ] Frontend: Angular, Svelte/SvelteKit, Astro
- [ ] Backend: Django, Spring Boot, Rails, Laravel, .NET, Elixir/Phoenix
- [ ] Mobile: Kotlin Multiplatform, native watchOS/Wear OS, mobile release engineering (Fastlane, store rollouts)
- [ ] Infra: AWS CDK, Pulumi, Kubernetes/Helm, GitHub Actions, Docker
- [ ] QA: Cypress, Maestro, Detox, k6 (load), pytest/Jest deep-dives
- [x] React · Vue · NestJS · FastAPI · Fastify · Go · Flutter · React Native · SwiftUI · Jetpack Compose · Terraform · Playwright · Appium · Stripe · GitHub Actions · Cypress
- [ ] Frontend: Angular, Svelte/SvelteKit, Astro
- [ ] Backend: Django, Spring Boot, Rails, Laravel, .NET, Elixir/Phoenix
- [ ] Mobile: Kotlin Multiplatform, native watchOS/Wear OS, mobile release engineering (Fastlane, store rollouts)
- [ ] Infra: AWS CDK, Pulumi, Kubernetes/Helm, Docker
- [x] React · Vue · NestJS · FastAPI · Fastify · Go · Flutter · React Native · SwiftUI · Jetpack Compose · Terraform · Playwright · Appium · Stripe · GitHub Actions · Cypress
- [ ] Infra: AWS CDK, Pulumi, Kubernetes/Helm, Docker
- [ ] QA: Maestro, Detox, k6 (load), pytest/Jest deep-dives
- [ ] QA: Maestro, Detox, k6 (load), pytest/Jest deep-dives
- [ ] Data: PostgreSQL, Redis, Kafka, dbt

## License

MIT

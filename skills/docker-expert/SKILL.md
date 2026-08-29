---
name: docker-expert
description: Use when working with Dockerfile, docker-compose.yml, .dockerignore, or multi-stage builds. Build, debug, secure, and optimize Docker 27+ images and Docker Compose services.
license: MIT
metadata:
  version: "0.1.0"
  category: infra
  frameworks: "Docker 27+, BuildKit"
  triggers: Dockerfile, docker-compose.yml, .dockerignore, multi-stage builds, BuildKit, docker compose
  related: engineering-rules
---

# Docker Expert

Build small, reproducible, non-root Docker images using Docker 27+ and BuildKit.

## When to Use This Skill

- Creating or changing a `Dockerfile`
- Creating or debugging a `docker-compose.yml` or `compose.yaml`
- Converting a single-stage image into a multi-stage production image
- Improving Docker build cache behavior or BuildKit usage
- Adding `.dockerignore`, health checks, or non-root execution
- Diagnosing Docker image-size, startup, networking, volume, or Compose issues

## Core Workflow

1. **Inspect the runtime contract** - identify the app start command, listening port, required files, environment variables, native dependencies, and health endpoint. Read existing Dockerfiles, Compose files, lockfiles, and `.dockerignore` before making changes.

2. **Design build and runtime stages** - separate build dependencies from runtime dependencies. Pin an explicit maintained base-image version, use named build stages, and copy only required runtime artifacts into the final image.

3. **Implement Dockerfile and ignore rules** - order layers from least frequently changed to most frequently changed: base image, OS packages, dependency manifests, dependency installation, then application source. Add `.dockerignore` before relying on `COPY . .`.

4. **Verify the image build** - run `docker build --progress=plain -t app:local .`; fix every reported issue and re-run until clean. Change only an application source file, rebuild, and confirm dependency installation is cached.

5. **Run the container** - run `docker run --rm --name app-local -p 8080:8080 app:local`, replacing `8080` with the real application port. Check logs with `docker logs app-local`, verify the endpoint, fix failures, and re-run until clean.

6. **Implement Compose configuration when needed** - use Compose for multi-service applications or local development. Define explicit services, ports, networks, volumes, health checks, and dependency readiness.

7. **Verify Compose configuration** - run `docker compose config`; fix every reported issue and re-run until clean. Then run `docker compose up --build --wait`, inspect `docker compose ps` and `docker compose logs`, verify the application endpoint, and run `docker compose down --volumes` after testing.

8. **Harden the final image** - run as an unprivileged user, avoid `latest` tags, do not copy secrets into the image, and add a health check for long-running HTTP services. Run `docker image inspect app:local`; fix identified security or runtime problems and re-run until clean.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Production Dockerfiles | `references/production-dockerfiles.md` | Creating, optimizing, or reviewing a Dockerfile |
| Compose development | `references/compose-development.md` | Working with Compose services, volumes, networks, or local dependencies |
| Security and health checks | `references/security-healthchecks.md` | Hardening an image, handling secrets, or adding health checks |

## Key Patterns

Use multi-stage builds so compilers, source code, and development dependencies do not ship in the runtime image:

```dockerfile
# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .
RUN npm run build

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production

RUN groupadd --system app && useradd --system --gid app app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev
COPY --from=build /app/dist ./dist

USER app
EXPOSE 8080
CMD ["node", "dist/server.js"]
```

Copy lockfiles before application source so dependency installation remains cached:

```dockerfile
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
```

Wait for healthy dependencies in Compose instead of treating container startup as readiness:

```yaml
services:
  api:
    build: .
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://localhost:8080/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

## Common Mistakes

- **Using a single-stage image** - build tools, source files, and development dependencies ship to production. Use a separate build stage and minimal runtime stage.
- **Copying source before installing dependencies** - every source change invalidates dependency layers. Copy lockfiles first, install dependencies, then copy source.
- **Using `latest` image tags** - builds are not reproducible. Use an explicit maintained tag such as `node:22-bookworm-slim`.
- **Running as root** - create and use an unprivileged runtime user.
- **Missing `.dockerignore`** - build contexts can include `node_modules`, Git history, test output, and secrets. Exclude files that are not needed.
- **Using `depends_on` as readiness** - startup order does not prove the dependency is ready. Define health checks and use `condition: service_healthy`.
# Docker Security and Health Checks

## Run as a non-root user

The final runtime image should not run the application as root.

```dockerfile
FROM node:22-bookworm-slim AS runtime
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app app

COPY --chown=app:app --from=build /app/dist ./dist
COPY --chown=app:app package.json package-lock.json ./

USER app
CMD ["node", "dist/server.js"]
```

Set file ownership during `COPY` instead of using a later recursive `chown`.
This keeps layers smaller and makes ownership intentional.

Verify the runtime user:

```bash
docker build -t app:local .
docker run --rm --entrypoint id app:local
```

The output must not show `uid=0(root)`.

## Pin base images

Never use floating tags such as these:

```dockerfile
FROM node:latest
FROM postgres
FROM python:3
```

Use an explicit maintained release tag:

```dockerfile
FROM node:22-bookworm-slim
FROM python:3.13-slim-bookworm
FROM postgres:17-bookworm
```

A digest can be used where strict image reproducibility is required:

```dockerfile
FROM node:22-bookworm-slim@sha256:replace-with-reviewed-digest
```

Update pinned versions deliberately through dependency maintenance, not by using
`latest`.

## Keep secrets out of images

Do not copy `.env`, private keys, cloud credentials, or `.npmrc` into an image.

Bad pattern:

```dockerfile
COPY . .
RUN npm ci
```

Use `.dockerignore` and BuildKit secret mounts instead.

```dockerfile
# syntax=docker/dockerfile:1.7

COPY package.json package-lock.json ./
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    --mount=type=cache,target=/root/.npm \
    npm ci
```

Build with the secret supplied at build time:

```bash
docker build --secret id=npmrc,src=$HOME/.npmrc -t app:local .
```

Do not store a secret value in an `ARG` or `ENV` instruction. Those values can
be exposed in image metadata or layer history.

Inspect image history:

```bash
docker history --no-trunc app:local
```

Fix any exposed credentials and rebuild until no secret appears.

## HTTP health checks

A health check must test real application readiness, not merely whether a process exists.

For an HTTP API with `curl` installed:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl --fail --silent http://localhost:8080/health || exit 1
```

For Node images without `curl`:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://localhost:8080/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
```

The health endpoint should return success only after required dependencies,
migrations, and critical configuration are ready.

Inspect status:

```bash
docker inspect --format='{{.State.Health.Status}}' app-local
docker inspect --format='{{json .State.Health.Log}}' app-local
```

Fix unhealthy status causes and rerun until the container is healthy.

## Runtime hardening with Compose

Use read-only filesystems and remove unneeded Linux capabilities when the
application supports it.

```yaml
services:
  api:
    build: .
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    ports:
      - "8080:8080"
```

Test the application after applying restrictions:

```bash
docker compose up --build --wait
docker compose exec api id
docker compose logs api
```

If the app needs writable paths, mount only the required path as a volume or
temporary filesystem. Do not disable `read_only` without identifying the exact
write requirement.

## Publish only required ports

Use `EXPOSE` to document the container port:

```dockerfile
EXPOSE 8080
```

Map host ports only in development or where external access is required:

```yaml
ports:
  - "8080:8080"
```

Do not publish database ports in production unless external access is required.

## Required review checklist

- Final application process uses a non-root user.
- Base images use explicit maintained tags.
- `.dockerignore` excludes secrets and local environment files.
- Secrets use BuildKit secret mounts when required during a build.
- No secret is visible in `docker history --no-trunc`.
- Long-running HTTP services define a real readiness health check.
- Health checks are verified with `docker inspect`.
- Runtime services use only necessary ports.
- Apply read-only filesystem and dropped capabilities when compatible.
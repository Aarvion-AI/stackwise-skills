# Production Dockerfiles

## Build context first

Docker sends the build context to the daemon before it executes the Dockerfile.
A large context slows every build and can accidentally include credentials.

Create a `.dockerignore` before using `COPY . .`:

```gitignore
.git
.github
node_modules
dist
coverage
.env
.env.*
*.log
Dockerfile*
docker-compose*.yml
compose*.yaml
README.md
```

Do not ignore files needed by the build, such as a lockfile, source directory,
configuration file, or generated schema that is not recreated in the build.

Check the context size during a build:

```bash
docker build --progress=plain -t app:local .
```

Fix ignored-file mistakes and rebuild until the build succeeds cleanly.

## Cache-safe Dockerfile order

Put stable layers before frequently changed layers.

```dockerfile
FROM node:22-bookworm-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .
RUN npm run build
```

Do not use this order:

```dockerfile
COPY . .
RUN npm ci
RUN npm run build
```

The second form reruns `npm ci` whenever any source file changes.

Verify cache reuse:

```bash
docker build -t app:local .
docker build -t app:local .
```

On the second build, the dependency installation layer should show `CACHED`.
Fix layer ordering and rerun until dependency layers are cached after source-only changes.

## Node.js multi-stage image

Use a build stage for compilation and a separate runtime stage.

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

Build and inspect the final image:

```bash
docker build -t node-app:local .
docker image inspect node-app:local
docker history node-app:local
```

The final stage must not contain the build output source tree, compiler packages,
or development dependencies unless the runtime explicitly needs them.

## Python multi-stage image

Build wheels in one stage, then install them in the runtime stage.

```dockerfile
# syntax=docker/dockerfile:1.7

FROM python:3.13-slim-bookworm AS build
WORKDIR /build

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.13-slim-bookworm AS runtime
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app app

COPY --from=build /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

COPY src ./src

USER app
EXPOSE 8000
CMD ["python", "-m", "src.main"]
```

Verify the runtime image starts:

```bash
docker build -t python-app:local .
docker run --rm -p 8000:8000 python-app:local
```

Fix import, permission, and missing-runtime-file problems before continuing.

## Go multi-stage image

Compile a static binary in the build stage and copy it into a small runtime stage.

```dockerfile
# syntax=docker/dockerfile:1.7

FROM golang:1.24-bookworm AS build
WORKDIR /src

COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download

COPY . .
RUN --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /app ./cmd/api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /app /app
EXPOSE 8080
ENTRYPOINT ["/app"]
```

Verify the binary runs under the final non-root image:

```bash
docker build -t go-app:local .
docker run --rm -p 8080:8080 go-app:local
```

## Required review checklist

- Use a pinned, maintained base-image tag.
- Use BuildKit cache mounts for package-manager caches where supported.
- Copy dependency manifests before source code.
- Use multi-stage builds when source compilation or asset generation occurs.
- Copy only runtime artifacts into the final stage.
- Add `.dockerignore` before broad `COPY` instructions.
- Build with `docker build --progress=plain`.
- Rebuild after a source-only change and confirm dependencies are cached.
- Run the image and verify the real application endpoint.
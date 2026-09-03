# Docker Compose Development

## Use the Compose specification

Use `compose.yaml` or `docker-compose.yml`. Do not add the obsolete top-level
`version` field. Compose detects the current Compose specification automatically.

Start with explicit service names and local ports:

```yaml
services:
  api:
    build:
      context: .
    ports:
      - "8080:8080"
```

Validate before starting anything:

```bash
docker compose config
```

Fix every validation error and re-run until clean.

## API and PostgreSQL example

Use named volumes for database data. Do not bind-mount the database data directory
from a host path unless there is a specific reason.

```yaml
services:
  api:
    build:
      context: .
      target: runtime
    environment:
      DATABASE_URL: postgresql://app:local-password@db:5432/app
      PORT: "8080"
    ports:
      - "8080:8080"
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://localhost:8080/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s

  db:
    image: postgres:17-bookworm
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: local-password
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  postgres-data:
```

Start and verify it:

```bash
docker compose up --build --wait
docker compose ps
docker compose logs api
curl http://localhost:8080/health
```

Fix build, startup, health-check, or connection failures and rerun until all
required services show healthy.

## Service networking

Every service in the same Compose project can reach another service by service name.

Use this inside the `api` container:

```text
postgresql://app:local-password@db:5432/app
```

Do not use `localhost` to connect from one container to another.
Inside the `api` container, `localhost` means the `api` container itself.

Inspect the created network:

```bash
docker compose exec api getent hosts db
docker network ls
```

## Development bind mounts

Bind mounts are useful for application source code during local development.
Do not use them in a production image definition.

```yaml
services:
  api:
    build:
      context: .
      target: development
    command: npm run dev
    ports:
      - "8080:8080"
    volumes:
      - .:/app
      - api-node-modules:/app/node_modules

volumes:
  api-node-modules:
```

The named `api-node-modules` volume avoids replacing Linux container dependencies
with host dependencies.

Verify a source edit triggers the expected application reload.

## Environment files

Use `.env.example` for non-secret defaults and document required variables.

```yaml
services:
  api:
    env_file:
      - .env
    environment:
      PORT: "8080"
```

Do not commit `.env` files that contain real credentials.
Do not bake environment values into the Dockerfile with `ENV` if they differ by
deployment environment.

## Profiles for optional tools

Use profiles for development-only tools such as a database UI or mail catcher.

```yaml
services:
  adminer:
    image: adminer:5
    profiles:
      - tools
    ports:
      - "8081:8080"
```

Start the optional service only when needed:

```bash
docker compose --profile tools up --build
```

## Clean shutdown

Run this after local testing:

```bash
docker compose down --volumes --remove-orphans
```

Use `--volumes` only when it is acceptable to remove local database data.

## Required review checklist

- Do not use the obsolete `version` field.
- Use service names for container-to-container connections.
- Add health checks for dependencies that must be ready.
- Use `condition: service_healthy` for readiness dependencies.
- Use named volumes for persistent service data.
- Keep local secrets outside Git.
- Use profiles for optional development tooling.
- Run `docker compose config` before `docker compose up`.
- Run `docker compose up --build --wait` and verify healthy services.
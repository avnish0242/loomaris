# Loomaris Backend

FastAPI backend for the Loomaris platform. Handles authentication, tenant management, and (in later phases) chat generation and deployment orchestration.

> For full project setup, see the [root README](../README.md).

---

## Running locally (without Docker)

Useful for rapid iteration on backend code without rebuilding containers.

### Requirements

- Python 3.12+
- PostgreSQL 16 running locally (or via Docker)
- Redis running locally (or via Docker)

### Setup

```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start just the infrastructure services (no backend container)
cd ..
docker compose -f docker-compose.dev.yml up postgres redis localstack -d
cd backend

# Run migrations
alembic upgrade head

# Seed test tenant
python scripts/seed_tenant.py

# Start the API server (hot reload)
uvicorn app.main:app --reload --port 8000
```

---

## Running via Docker (standard)

From the project root:

```bash
make dev-build   # first run (builds image)
make dev         # subsequent runs
make migrate     # run migrations
make seed        # seed test tenant
```

---

## Project layout

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, middleware, router registration
│   ├── database.py             # SQLAlchemy async engine + session factory
│   ├── core/
│   │   ├── config.py           # All settings via pydantic-settings (reads .env.local)
│   │   └── security.py         # create_access_token, decode_access_token, encrypt/decrypt
│   ├── models/
│   │   └── platform.py         # Organization, User, OrgMembership, CloudAccount ORM models
│   ├── api/
│   │   ├── deps.py             # get_current_user FastAPI dependency
│   │   └── routes/
│   │       ├── auth.py         # Google OAuth callback, /me, /claude-key
│   │       └── health.py       # /health, /health/db
│   ├── services/
│   │   ├── auth_service.py     # get_or_create_user, store_anthropic_key, get_anthropic_key
│   │   └── tenant_service.py   # create_org_schema, get_or_create_default_org, add_user_to_org
│   └── workers/                # Celery tasks (Phase 2: deploy_task.py, cost_task.py)
├── alembic/
│   ├── env.py                  # Async Alembic env; reads DATABASE_URL from settings
│   └── versions/
│       └── 001_initial_platform_schema.py
├── scripts/
│   └── seed_tenant.py          # Seeds Loomaris Labs org + LocalStack cloud account
├── alembic.ini
├── requirements.txt
└── Dockerfile
```

---

## Database design

All platform-wide tables live in the `platform` schema. Each organisation gets its own schema (`org_{slug}`) created dynamically on registration.

```
platform.organizations       — org registry
platform.users               — users (google_sub, encrypted API keys)
platform.org_memberships     — user ↔ org ↔ role
platform.cloud_accounts      — BYO cloud accounts (vault_path references Vault KV)

org_loomaris_labs.apps
org_loomaris_labs.chat_sessions
org_loomaris_labs.chat_turns      — each turn = one git commit
org_loomaris_labs.deployments
org_loomaris_labs.cost_estimates
org_loomaris_labs.audit_log
```

### Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Generate a new migration (autogenerate from model changes)
alembic revision --autogenerate -m "add_xyz_table"
```

---

## Authentication flow

```
1. GET /api/v1/auth/google
   → redirects to Google consent screen

2. GET /api/v1/auth/google/callback?code=XXX
   → exchanges code for tokens
   → creates/updates user in DB (google_refresh_token stored Fernet-encrypted)
   → auto-joins user to Loomaris Labs org (Phase 1 single-org)
   → issues JWT (60 min)
   → dev: shows success page with token + redirects to /docs
   → prod: redirects to FRONTEND_URL/auth/callback?access_token=...

3. Subsequent requests: Authorization: Bearer <token>
   → decoded in api/deps.py → get_current_user dependency

4. POST /api/v1/auth/claude-key {"api_key": "sk-ant-..."}
   → stored Fernet-encrypted in platform.users.anthropic_api_key_enc
   → used by generation engine; falls back to ANTHROPIC_API_KEY env var
```

---

## Key services

### `auth_service.get_anthropic_key(db, user_id)`
Returns the decrypted Anthropic API key for the user. Priority:
1. User's own key (stored encrypted in DB after `POST /claude-key`)
2. `ANTHROPIC_API_KEY` environment variable (master key, Phase 1 fallback)

### `tenant_service.create_org_schema(db, org_slug)`
Creates `org_{slug}` schema + all per-org tables (apps, chat_sessions, chat_turns, deployments, cost_estimates, audit_log). Idempotent — safe to call multiple times.

### `security.encrypt_value` / `decrypt_value`
Fernet symmetric encryption using `ENCRYPTION_KEY` from settings. Used for Google refresh tokens and Anthropic API keys stored in the DB.

---

## Adding new migrations

```bash
# Inside the backend container (or locally with venv active):
alembic revision --autogenerate -m "describe_your_change"

# Review the generated file in alembic/versions/, then apply:
alembic upgrade head
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn[standard]` | ASGI server |
| `sqlalchemy[asyncio]` + `asyncpg` | Async PostgreSQL ORM |
| `alembic` | DB migrations |
| `pydantic-settings` | Settings from env files |
| `authlib` | Google OAuth 2.0 (OIDC) |
| `python-jose[cryptography]` | JWT encode/decode |
| `cryptography` | Fernet encryption for secrets at rest |
| `anthropic` | Claude API client |
| `boto3` | AWS SDK (LocalStack in dev, real AWS in prod) |
| `celery[redis]` | Async task queue (Phase 2) |

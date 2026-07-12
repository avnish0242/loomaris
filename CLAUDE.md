# Loomaris — Claude Code Reference

AI-powered app generation platform. Users describe what they want in chat; Claude generates the code (streamed token-by-token), commits it to a per-app git repo, and can deploy it to the user's own AWS account via Pulumi IaC.

---

## Repo layout

```
loomaris/
├── backend/          FastAPI + Celery (Python 3.12, Poetry)
├── frontend/         Next.js 14 App Router (TypeScript)
├── infrastructure/
│   ├── terraform/    Full prod infra (ECS, ALB, RDS, ECR, WAF…)
│   └── pulumi-runner/ Sandboxed Pulumi execution container
├── docker-compose.dev.yml
└── Makefile          All dev + prod commands
```

---

## Running locally

```bash
make dev-build   # first run
make dev         # subsequent runs
make migrate     # apply Alembic migrations
make seed        # seed dev tenant + owner
```

Services: frontend :3000, backend :8000, Flower :5555, Postgres :5432, Redis :6379, LocalStack :4566.

Backend hot-reloads via uvicorn `--reload`. Frontend hot-reloads via Next.js dev server.

---

## Backend conventions

### Dependency management
Poetry only — no `requirements.txt`. Add packages with `make poetry-add name=<pkg>`.

### Settings
All config lives in `backend/app/core/config.py` as a `pydantic_settings.BaseSettings` class, `lru_cache`'d. Access via `from app.core.config import settings`. Changing env vars requires a container recreate (`make reload-backend`), not a restart.

### Database
Async SQLAlchemy 2.0 throughout. Session factory in `backend/app/database.py`. Always `await db.commit()` + `await db.refresh(obj)` after writes.

**Multi-tenant schema routing:** every org gets its own PostgreSQL schema named `org_{slug_with_underscores}`. The `get_db` dependency (`backend/app/api/deps.py`) sets `search_path = org_{slug}, platform, public` on each connection based on the JWT's `org_id` claim. Platform-wide tables (users, orgs, memberships, cloud accounts) live in the `platform` schema.

### Auth dependencies
- `get_current_user` — validates Bearer JWT, returns `User`
- `require_org_admin` — requires `role in (owner, admin)` in the user's active membership
- `require_superadmin` — requires `user.is_superadmin = True`

### Encryption
Fernet symmetric encryption (`backend/app/core/security.py`) is used for all secrets stored in the DB: cloud credentials, per-org Anthropic API keys, OAuth tokens. Never store plaintext credentials in the database.

### Adding a migration

```bash
make shell
alembic revision --autogenerate -m "describe_the_change"
# review the generated file in backend/alembic/versions/
alembic upgrade head
```

### Adding a new route file
1. Create `backend/app/api/routes/myroute.py` with `router = APIRouter(prefix="/myprefix", tags=["mytag"])`
2. Register in `backend/app/main.py`: `app.include_router(myroute.router, prefix="/api/v1")`

### Celery tasks
Workers are in `backend/app/workers/`. Each task file registers tasks against `celery_app` from `celery_app.py`. Queues: `deploy`, `cost`, `scan`. Add new task modules to the `include` list in `celery_app.py`.

---

## Frontend conventions

### Auth flow (prod)
1. User clicks "Sign in with Google/GitHub" on `/login`
2. Backend initiates OAuth redirect
3. After OAuth, backend redirects to `https://app.loomaris.xyz/auth/callback?token=JWT&next=/chat`
4. `/auth/callback` reads `?token=`, saves to `localStorage` as `loomaris_token`, redirects to `next`
5. `AuthGuard` component validates the token via `GET /api/v1/auth/me` and routes based on `membership_status`

**Auth flow (dev):** Backend redirects to `http://localhost:3000/#token=JWT&next=/chat` (hash fragment). The landing page (`app/page.tsx`) and `consumeAuthHash()` in `auth.ts` handle this.

### API client
All API calls go through `frontend/src/lib/api.ts`. Every function reads the token via `authHeaders()` from `auth.ts`. Add new endpoints here; don't inline fetch calls in components.

### SSE streaming
Use the async generator in `frontend/src/lib/stream.ts` for all SSE endpoints (chat generation, deploy stream). It handles reconnection and chunk parsing.

### Routing after login
`AuthGuard` maps `membership_status` → route:
- `active` → render children (stay in `/chat`)
- `pending` → `/waiting`
- `none` + superadmin → `/admin`
- `none` + normal user → `/onboarding`

---

## Key service responsibilities

| Service | File | What it does |
|---|---|---|
| `chat_service` | `services/chat_service.py` | Streams Claude response, writes git commit per turn, generates session title |
| `auth_service` | `services/auth_service.py` | `get_or_create_user`, encrypted key storage/retrieval |
| `tenant_service` | `services/tenant_service.py` | DDL: create per-org PostgreSQL schema + tables |
| `org_service` | `services/org_service.py` | Org CRUD, invite tokens, join-request lifecycle |
| `cloud_service` | `services/cloud_service.py` | AWS STS validation, Fernet-encrypt credentials to DB |
| `deploy_service` | `services/deploy_service.py` | Docker-outside-of-Docker local preview deploy |
| `guardrail_service` | `services/guardrail_service.py` | Pre-prompt classifier: regex rules → Claude Haiku LLM layer |
| `scanner_service` | `services/scanner_service.py` | Post-gen Semgrep + detect-secrets on generated code |
| `sim_service` | `services/sim_service.py` | ECS Fargate simulation session lifecycle |
| `cost_engine/` | `services/cost_engine/` | AWS + Azure pricing APIs, tier projector, hard-cap enforcer |
| `iac/` | `services/iac/` | IaC generator (Pulumi), validator (AST + Semgrep), runner, AWS templates |

---

## Production deploy

Prod is AWS ECS Fargate behind an ALB. All infra in `infrastructure/terraform/`.

```bash
make ecr-push      # build linux/amd64 images → push to ECR (both backend + frontend)
make ecs-migrate   # run alembic upgrade head as one-off ECS task
make ecs-status    # check running task counts
```

CI/CD: push to `main` triggers `.github/workflows/deploy.yml` — lints, builds per-service images tagged with `$GITHUB_SHA`, registers new ECS task definitions, deploys, runs migrations, waits for stable.

### ECS troubleshooting
If the frontend circuit breaker trips (service stuck at 0/1):
```bash
aws ecs update-service --cluster loomaris --service loomaris-frontend \
  --force-new-deployment \
  --deployment-configuration "deploymentCircuitBreaker={enable=false,rollback=false},maximumPercent=200,minimumHealthyPercent=0"
```

---

## What's implemented vs not

### Working
- Google + GitHub OAuth, JWT, multi-org RBAC
- Schema-per-org tenant provisioning
- Claude streaming code generation with git commits per turn
- Chat sessions + history
- AWS cloud account connect (STS cross-account role, Fernet-encrypted in DB)
- Org onboarding, invite/join-request flows, superadmin panel
- Cost engine services (AWS + Azure pricing APIs, tier projector, cap enforcer)
- IaC generator/validator/runner code (Pulumi Python SDK)
- Celery worker stubs (deploy, cost, scan, simulate, destroy)
- Guardrail (rule + Haiku) and scanner (Semgrep) services
- Simulation session scaffolding (ECS Fargate)
- Full Terraform prod infra (ECS, ALB, RDS, ElastiCache, WAF, Route53, CloudFront)
- CI/CD pipeline (GitHub Actions → ECR → ECS)

### Not yet end-to-end functional
- **Cloud deploy loop** — Pulumi execution against real user AWS account isn't wired end-to-end yet; `deploy_task.py` has the IaC pipeline but needs real Pulumi execution connected
- **Azure/GCP cloud accounts** — only AWS is implemented
- **Live preview URL** — deploy_task returns status but live endpoint URL isn't surfaced in UI
- **Rollback** — route exists, implementation is a stub
- **Export** — route exists, S3 signed URL not yet wired
- **Billing** — not started (Phase 3)
- **Vault** — using Fernet-in-DB instead; Vault is Phase 3
- **Firecracker runners** — pulumi-runner Docker container exists; Firecracker is Phase 3
- **Observability** — CloudWatch logs only; Prometheus/Grafana not set up

---

## Common tasks

**Add a new API endpoint:**
1. Add handler to appropriate route file in `backend/app/api/routes/`
2. Add corresponding TypeScript function to `frontend/src/lib/api.ts`
3. If it needs a Celery task, add it to `backend/app/workers/` and register in `celery_app.py`

**Change the Claude model:**
Update `model=` in `backend/app/services/chat_service.py`. Current models: `claude-sonnet-4-6` (generation), `claude-haiku-4-5-20251001` (titles + guardrail).

**Add a new org plan tier:**
1. Update the plan enum/validator in `backend/app/models/platform.py`
2. Add resource limits in `backend/app/services/iac/validator.py` (`ALLOWED_RESOURCES_BY_PLAN`)
3. Update cost cap defaults in `tenant_service.py`

**Promote a user to superadmin:**
```bash
make shell
python scripts/seed_superadmin.py avnish.dbg@gmail.com
```

**Test prod auth locally:**
Set `APP_ENV=production` in `.env.local` — this switches the OAuth redirect from hash-fragment mode to `/auth/callback?token=` query-param mode.

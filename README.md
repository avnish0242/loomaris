# Loomaris

AI-powered application generation platform. Describe what you want to build in plain English — get production-ready code committed to git, deployed to your own cloud account. Powered by Claude API.

> Full system design: [`architecture-blueprint.md`](./architecture-blueprint.md)

---

## Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (async), SQLAlchemy 2.0 async, asyncpg, Alembic, Poetry |
| **Frontend** | Next.js 14 App Router, TypeScript, Tailwind CSS |
| **Database** | PostgreSQL 16 (schema-per-org tenancy) |
| **AI** | Anthropic Claude (Sonnet for generation, Haiku for titles + guardrail) |
| **Auth** | Google OAuth 2.0 + GitHub OAuth via Authlib, JWT (python-jose) |
| **Encryption** | Fernet symmetric (API keys, OAuth tokens, AWS credentials at rest) |
| **Code Storage** | gitpython — each app gets its own git repo at `/repos/{slug}` |
| **Task Queue** | Celery + Redis (deploy, cost, scan, simulate, destroy workers) |
| **IaC** | Pulumi Python SDK (generator + validator + runner), custom AWS templates |
| **Cost Engine** | AWS Price List API + Azure Retail Prices, tier projector, hard-cap enforcer |
| **Dev Infra** | Docker Compose, LocalStack Pro (S3, STS, KMS, SecretsManager) |
| **Prod Infra** | AWS ECS Fargate, ALB, RDS, ElastiCache, ECR — all via Terraform |
| **CI/CD** | GitHub Actions → ECR push → ECS task-definition update |

---

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| **Docker runtime** | Runs all services | [OrbStack](https://orbstack.dev) (recommended) or [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| **Python 3.12+** | `make setup` key generation | `brew install python` |
| **LocalStack CLI** | Auto-read auth token | `brew install localstack/tap/localstack-cli` |
| **AWS CLI** | Prod deploys + ECR push | `brew install awscli` |
| **Terraform** | Provision prod infra | `brew install terraform` |
| **Google OAuth credentials** | User authentication | [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) |
| **GitHub OAuth credentials** | GitHub sign-in | [github.com/settings/developers](https://github.com/settings/developers) |
| **Anthropic API key** | Claude generation (or stored per-user after login) | [console.anthropic.com](https://console.anthropic.com) |

---

## Quickstart

### 1. Clone and set up

```bash
git clone <repo-url> loomaris
cd loomaris
make setup
```

`make setup` automatically:
- Copies `.env.example` → `.env.local`
- Reads your LocalStack auth token via `localstack auth token`
- Generates `ENCRYPTION_KEY` (Fernet) and `JWT_SECRET_KEY` (hex) if still placeholders

### 2. Configure OAuth

**Google OAuth:**
1. [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. **Create Credentials → OAuth 2.0 Client ID** → Web application
3. Authorised redirect URI: `http://localhost:8000/api/v1/auth/google/callback`
4. Add to `.env.local`:
```
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

**GitHub OAuth:**
1. [GitHub → Settings → Developer settings → OAuth Apps → New OAuth App](https://github.com/settings/developers)
2. Homepage URL: `http://localhost:3000`
3. Callback URL: `http://localhost:8000/api/v1/auth/github/callback`
4. Add to `.env.local`:
```
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
```

### 3. Start services

```bash
make dev-build    # first run (builds images)
make dev          # subsequent runs
```

| Service | URL | Purpose |
|---|---|---|
| **Frontend** | http://localhost:3000 | Next.js app |
| **Backend API** | http://localhost:8000 | FastAPI |
| **API Docs** | http://localhost:8000/docs | Swagger UI |
| **Celery Flower** | http://localhost:5555 | Task queue dashboard |
| **PostgreSQL** | localhost:5432 | Database |
| **Redis** | localhost:6379 | Task broker |
| **LocalStack** | http://localhost:4566 | AWS emulation (S3, STS, KMS, SecretsManager) |

### 4. Run migrations + seed

```bash
make migrate    # creates platform schema + tables
make seed       # creates Loomaris Labs dev tenant + owner user
```

### 5. Log in

Open http://localhost:3000 and sign in via Google or GitHub. Your account is auto-joined to **Loomaris Labs** as owner. The frontend prompts for a Claude API key on first login.

---

## Daily development

```bash
make dev              # start all services
make dev-build        # rebuild + start (after Dockerfile / dependency changes)
make reload-backend   # force-recreate backend only (after .env.local changes)
make logs             # tail backend + celery logs
make migrate          # apply new Alembic migrations
make migrate-down     # roll back one migration
make seed             # re-seed dev tenant
make shell            # bash inside backend container
make psql             # psql into PostgreSQL
make down             # stop all services
make lint             # ruff + pyright
```

---

## Project structure

```
loomaris/
├── architecture-blueprint.md       # Full system design
├── docker-compose.dev.yml          # Dev stack (all services)
├── docker-compose.prod.yml         # Prod stack (nginx fallback)
├── Makefile                        # All commands
├── .env.example                    # Template (copy → .env.local, never commit)
├── .env.production                 # Prod env template — gitignored, fill in on server
│
├── .github/
│   └── workflows/
│       └── deploy.yml              # CI/CD: lint → ECR push → ECS deploy → migrate
│
├── backend/
│   ├── pyproject.toml              # Poetry dependencies
│   ├── poetry.lock
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, router registration
│   │   ├── database.py             # Async SQLAlchemy engine + session factory
│   │   ├── core/
│   │   │   ├── config.py           # Pydantic settings (lru_cache)
│   │   │   └── security.py         # JWT + Fernet encryption helpers
│   │   ├── models/
│   │   │   ├── platform.py         # Organization, User, OrgMembership, CloudAccount
│   │   │   └── org.py              # App, ChatSession, ChatTurn, Deployment, SimSession
│   │   ├── api/
│   │   │   ├── deps.py             # get_current_user, require_org_admin, require_superadmin
│   │   │   └── routes/
│   │   │       ├── auth.py         # Google + GitHub OAuth, /me, /claude-key
│   │   │       ├── orgs.py         # Org CRUD, membership, invites, join requests
│   │   │       ├── admin.py        # Superadmin: list/suspend orgs, manage users
│   │   │       ├── apps.py         # Apps CRUD, files/git, local deploy SSE, cloud deploy, rollback, export, simulate, cost
│   │   │       ├── chat.py         # Chat sessions + streaming generation
│   │   │       ├── cloud.py        # Cloud account connect/verify/list/delete
│   │   │       └── health.py       # /health, /health/db
│   │   ├── services/
│   │   │   ├── auth_service.py     # User create/login, API key storage
│   │   │   ├── tenant_service.py   # Per-org schema provisioning (DDL)
│   │   │   ├── org_service.py      # Org CRUD, invite + join-request workflows
│   │   │   ├── chat_service.py     # Stream chat, git commit, session title generation
│   │   │   ├── git_service.py      # Per-app git repos, commit, zip archive
│   │   │   ├── deploy_service.py   # Docker-outside-of-Docker local preview deploy
│   │   │   ├── cloud_service.py    # AWS STS validation, Fernet-encrypted credential storage
│   │   │   ├── guardrail_service.py  # Pre-prompt intent classifier (rule + Haiku LLM layer)
│   │   │   ├── scanner_service.py  # Post-gen Semgrep + secret detection
│   │   │   ├── sim_service.py      # ECS Fargate simulation session lifecycle
│   │   │   ├── permission_actions.py  # IAM permission template definitions
│   │   │   ├── cost_engine/
│   │   │   │   ├── aggregator.py   # Multi-cloud pricing orchestrator
│   │   │   │   ├── aws_pricing.py  # AWS Price List API client
│   │   │   │   ├── azure_pricing.py  # Azure Retail Prices API client
│   │   │   │   ├── tier_projector.py  # Traffic-tier cost projections
│   │   │   │   └── cap_enforcer.py # Org hard-cap check + enforcement
│   │   │   └── iac/
│   │   │       ├── generator.py    # Claude-driven Pulumi program generator
│   │   │       ├── validator.py    # Pulumi AST + Semgrep IaC rule validator
│   │   │       ├── runner.py       # Pulumi preview + apply execution
│   │   │       ├── detector.py     # App-type detection from generated files
│   │   │       └── aws_templates.py  # Pre-validated Pulumi component templates
│   │   └── workers/
│   │       ├── celery_app.py       # Celery app + broker config
│   │       ├── deploy_task.py      # Cloud deploy: IaC gen → validate → preview → apply
│   │       ├── cost_task.py        # Async cost estimation task
│   │       ├── scan_task.py        # Async post-gen code scanner
│   │       ├── simulate_task.py    # ECS simulation session manager
│   │       └── destroy_task.py     # Tear down cloud resources
│   ├── alembic/versions/
│   │   ├── 001_initial_platform_schema.py
│   │   ├── 002_cloud_account_credentials.py
│   │   ├── 003_phase2_indexes_and_rls.py
│   │   ├── 004_phase3_auth_onboarding.py
│   │   ├── 005_sts_cross_account.py
│   │   └── 006_simulation_sessions.py
│   ├── scripts/
│   │   ├── seed_tenant.py          # Seed Loomaris Labs dev tenant
│   │   └── seed_superadmin.py      # Promote a user to superadmin
│   └── semgrep-rules/
│       └── loomaris-iac.yaml       # Custom Semgrep rules for IaC security
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # Landing page (typewriter demo, features, about)
│   │   │   ├── login/page.tsx      # Google + GitHub sign-in page
│   │   │   ├── auth/callback/page.tsx  # OAuth token handler
│   │   │   ├── onboarding/page.tsx # New user: create or join an org
│   │   │   ├── waiting/page.tsx    # Pending org approval screen
│   │   │   ├── admin/page.tsx      # Superadmin org management panel
│   │   │   └── chat/
│   │   │       ├── layout.tsx      # AuthGuard, Claude key modal, cloud modal
│   │   │       ├── page.tsx        # /chat home (create session + redirect)
│   │   │       └── [sessionId]/page.tsx  # Chat + code panel + deploy panel
│   │   ├── components/
│   │   │   ├── AuthGuard.tsx       # JWT validation + membership routing
│   │   │   ├── Sidebar.tsx         # Session list, org info, cloud status
│   │   │   ├── MessageBubble.tsx   # Chat message rendering (markdown)
│   │   │   ├── ActionBar.tsx       # Per-message action bar (copy, deploy, etc.)
│   │   │   ├── CodeDrawer.tsx      # Slide-out file browser + syntax viewer
│   │   │   ├── DeployPanel.tsx     # Local Docker deploy SSE stream + status
│   │   │   ├── DeployModal.tsx     # Cloud deploy confirmation + cost preview
│   │   │   ├── PreviewPane.tsx     # Deployed app iframe preview
│   │   │   ├── ApiKeyModal.tsx     # Claude API key setup
│   │   │   ├── CloudConnectModal.tsx  # AWS credential connect (STS validated)
│   │   │   └── PermissionTemplateModal.tsx  # IAM permission template picker
│   │   └── lib/
│   │       ├── api.ts              # All API client functions + TypeScript types
│   │       ├── auth.ts             # localStorage JWT helpers + OAuth hash parser
│   │       ├── stream.ts           # fetch-based SSE async generator
│   │       └── permission-templates.ts  # IAM permission template definitions
│   ├── Dockerfile                  # Dev (hot-reload)
│   └── Dockerfile.prod             # Multi-stage production build (Next.js standalone)
│
└── infrastructure/
    ├── terraform/                  # Full prod infra: VPC, ECS, ALB, RDS, ECR, IAM, WAF
    │   ├── main.tf / variables.tf / outputs.tf
    │   ├── ecs_backend.tf / ecs_frontend.tf / ecs_cluster.tf
    │   ├── alb.tf / acm.tf / route53.tf / cloudflare_dns.tf
    │   ├── rds.tf / elasticache.tf / s3.tf / kms.tf
    │   ├── iam.tf / security_groups.tf / vpc.tf / vpc_endpoints.tf
    │   ├── waf.tf / budgets.tf / secrets.tf / ecr.tf
    │   └── sim_account/            # Separate Terraform root for simulation AWS account
    ├── pulumi-runner/
    │   └── Dockerfile              # Sandboxed Pulumi execution container
    ├── nginx/                      # nginx config (used in docker-compose prod fallback)
    ├── certbot/                    # Let's Encrypt bootstrap (docker-compose prod)
    └── localstack/
        └── init-aws.sh             # Creates S3 buckets + KMS key on LocalStack start
```

---

## API reference

### Auth
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/health` | — | Service health |
| `GET` | `/api/v1/health/db` | — | DB connectivity |
| `GET` | `/api/v1/auth/google` | — | Initiate Google OAuth |
| `GET` | `/api/v1/auth/google/callback` | — | Google OAuth callback |
| `GET` | `/api/v1/auth/github` | — | Initiate GitHub OAuth |
| `GET` | `/api/v1/auth/github/callback` | — | GitHub OAuth callback |
| `GET` | `/api/v1/auth/me` | Bearer | Current user + org + flags |
| `POST` | `/api/v1/auth/claude-key` | Bearer | Store Anthropic key (encrypted) |
| `GET` | `/api/v1/auth/claude-key/status` | Bearer | Check if Claude key is set |

### Orgs
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/orgs` | Bearer | List orgs (public info for join screen) |
| `POST` | `/api/v1/orgs` | Bearer | Create a new org |
| `POST` | `/api/v1/orgs/join-request` | Bearer | Request to join an org |
| `GET` | `/api/v1/orgs/{id}/join-requests` | Org admin | List pending join requests |
| `POST` | `/api/v1/orgs/{id}/join-requests/{uid}/approve` | Org admin | Approve join request |
| `POST` | `/api/v1/orgs/{id}/join-requests/{uid}/reject` | Org admin | Reject join request |
| `POST` | `/api/v1/orgs/{id}/invite` | Org admin | Invite user by email |
| `GET` | `/api/v1/orgs/invite/{token}` | Bearer | Accept an org invite |
| `GET` | `/api/v1/orgs/{id}/members` | Org admin | List org members |
| `DELETE` | `/api/v1/orgs/{id}/members/{uid}` | Org admin | Remove a member |

### Admin (superadmin only)
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/admin/orgs` | Superadmin | List all orgs with stats |
| `POST` | `/api/v1/admin/orgs/{id}/suspend` | Superadmin | Suspend an org |
| `POST` | `/api/v1/admin/orgs/{id}/unsuspend` | Superadmin | Unsuspend an org |
| `GET` | `/api/v1/admin/users` | Superadmin | List all users |
| `POST` | `/api/v1/admin/users/{uid}/make-superadmin` | Superadmin | Grant superadmin |
| `POST` | `/api/v1/admin/orgs/{id}/members/{uid}/promote` | Superadmin | Promote to org admin |

### Apps
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/apps` | Bearer | Create app |
| `GET` | `/api/v1/apps` | Bearer | List apps |
| `GET` | `/api/v1/apps/{id}` | Bearer | Get app |
| `GET` | `/api/v1/apps/{id}/sessions` | Bearer | List chat sessions |
| `GET` | `/api/v1/apps/{id}/files` | Bearer | Current files from git |
| `GET` | `/api/v1/apps/{id}/archive` | Bearer | Download zip |
| `GET` | `/api/v1/apps/{id}/deploy/status` | Bearer | Local Docker container status |
| `POST` | `/api/v1/apps/{id}/deploy` | Bearer | Local Docker deploy (SSE stream) |
| `DELETE` | `/api/v1/apps/{id}/preview` | Bearer | Stop local preview container |
| `POST` | `/api/v1/apps/{id}/cloud-deploy` | Bearer | Async cloud deploy via Pulumi |
| `POST` | `/api/v1/apps/{id}/preflight` | Bearer | Verify IAM permissions |
| `POST` | `/api/v1/apps/{id}/rollback` | Bearer | Roll back to previous deployment/commit |
| `POST` | `/api/v1/apps/{id}/export` | Bearer | Export source + IaC as ZIP (S3 signed URL) |
| `POST` | `/api/v1/apps/{id}/cost-estimate` | Bearer | Async multi-cloud cost estimate |
| `POST` | `/api/v1/apps/{id}/simulate` | Bearer | Start ECS Fargate simulation session |
| `GET` | `/api/v1/apps/{id}/simulate/status` | Bearer | Poll simulation status |
| `DELETE` | `/api/v1/apps/{id}/simulate` | Bearer | Stop simulation session |

### Chat
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/chat/sessions` | Bearer | List all chat sessions |
| `POST` | `/api/v1/chat/sessions` | Bearer | Create session |
| `GET` | `/api/v1/chat/sessions/{id}/history` | Bearer | Chat history |
| `POST` | `/api/v1/chat/sessions/{id}/message` | Bearer | Send message (SSE stream) |

### Cloud accounts
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/cloud/accounts` | Bearer | Connect AWS/Azure account |
| `GET` | `/api/v1/cloud/accounts` | Bearer | List connected accounts |
| `DELETE` | `/api/v1/cloud/accounts/{id}` | Bearer | Remove account |
| `POST` | `/api/v1/cloud/accounts/{id}/verify` | Bearer | Re-verify credentials |

Full interactive docs: **http://localhost:8000/docs**

---

## Key environment variables

See [`.env.example`](.env.example) for the full list.

| Variable | Required | Auto-set | Description |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | Yes | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | — | Google OAuth client secret |
| `GITHUB_CLIENT_ID` | Yes | — | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | Yes | — | GitHub OAuth client secret |
| `ANTHROPIC_API_KEY` | Recommended | — | Master Claude key (per-org keys in DB override) |
| `SUPERADMIN_EMAIL` | Dev | — | Email to auto-promote to superadmin on first login |
| `LOCALSTACK_AUTH_TOKEN` | Dev only | `make setup` | LocalStack Pro auth |
| `ENCRYPTION_KEY` | Yes | `make setup` | Fernet key for secrets at rest |
| `JWT_SECRET_KEY` | Yes | `make setup` | JWT signing key |
| `LOOMARIS_DEPLOYER_ACCESS_KEY` | Prod | — | IAM key for cross-account STS assume-role |
| `LOOMARIS_DEPLOYER_SECRET_KEY` | Prod | — | IAM secret for cross-account STS |

---

## Production deployment (loomaris.xyz)

Prod runs on AWS ECS Fargate behind an ALB. Infrastructure is managed with Terraform.

### First-time infra setup

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in values
terraform init
terraform plan
terraform apply
```

### Deploy application

```bash
# Build + push backend and frontend images to ECR
make ecr-push

# Run DB migrations on ECS
make ecs-migrate

# Check ECS service health
make ecs-status
```

Or push to `main` — the GitHub Actions workflow handles everything automatically.

### CI/CD flow (GitHub Actions → `main`)

1. Lint (`ruff`)
2. Build backend image → tag with `$GITHUB_SHA` → push to ECR
3. Register new ECS task definition with the new image
4. Update `loomaris-backend` ECS service
5. Run `alembic upgrade head` as a one-off ECS task
6. Same for frontend (steps 2–4)
7. Wait for both services to stabilize

### Prod services

| Domain | Service |
|---|---|
| `app.loomaris.xyz` | Next.js frontend (ECS Fargate) |
| `api.loomaris.xyz` | FastAPI backend (ECS Fargate) |

---

## Troubleshooting

**`make dev` → `docker: No such file or directory`**
Install Docker: `brew install --cask orbstack` then open OrbStack.

**`make migrate` → connection refused**
Backend isn't up yet. Run `make dev` first, wait for healthy, then migrate in a new terminal.

**`make reload-backend` not picking up new env vars**
Use `--force-recreate` (what `reload-backend` does). Do not use `restart` — `lru_cache` on Settings requires a full container recreate.

**Google/GitHub OAuth → redirect_uri_mismatch**
Redirect URI in the OAuth app settings must exactly match the `*_REDIRECT_URI` in `.env.local`.

**`ENCRYPTION_KEY is not set`**
Run `make setup`. Or manually:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**AWS STS validation fails in cloud connect modal**
Check the IAM role trust policy has the Loomaris deployer account as a principal, and the role has at least `sts:AssumeRole` + `sts:GetCallerIdentity`.

**ECS frontend 503 / circuit breaker tripped**
```bash
# Force new deployment with circuit breaker disabled
aws ecs update-service --cluster loomaris --service loomaris-frontend \
  --force-new-deployment \
  --deployment-configuration "deploymentCircuitBreaker={enable=false,rollback=false},maximumPercent=200,minimumHealthyPercent=0"
```

---

## Implementation status

| Phase | Status | Scope |
|---|---|---|
| **Phase 1 — Local MVP** | ✅ Complete | Auth (Google + GitHub), code gen, git, local Docker deploy, cloud account connect |
| **Phase 2 — Cloud Deploy** | 🔄 In progress | Multi-org, Celery workers, cost engine, IaC generator/validator, guardrails, scanner, simulation sessions, Terraform infra |
| **Phase 3 — Enterprise** | Planned | Stripe billing, Vault credentials, Firecracker runners, SAML SSO, AST-aware editing, SOC 2 |

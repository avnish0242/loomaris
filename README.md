# Loomaris

AI-powered application generation platform. Describe what you want to build in plain English — get production-ready code committed to git, deployed to your own cloud account. Powered by Claude API.

> Full system design: [`architecture-blueprint.md`](./architecture-blueprint.md)

---

## Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (async), SQLAlchemy 2.0 async, asyncpg, Alembic |
| **Frontend** | Next.js 14 App Router, TypeScript, Tailwind CSS |
| **Database** | PostgreSQL 16 (schema-per-org tenancy) |
| **AI** | Anthropic Claude (Sonnet for generation, Haiku for titles) |
| **Auth** | Google OAuth 2.0 via Authlib, JWT (python-jose) |
| **Encryption** | Fernet symmetric (API keys, OAuth tokens, AWS credentials) |
| **Code Storage** | gitpython — each app gets its own git repo at `/repos/{slug}` |
| **Deploy** | Docker-outside-of-Docker for local preview; Pulumi IaC for Phase 2 cloud |
| **Infra** | Docker Compose (dev), nginx + Let's Encrypt (prod), LocalStack (dev AWS) |

---

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| **Docker runtime** | Runs all services | [OrbStack](https://orbstack.dev) (recommended) or [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| **Python 3.12+** | `make setup` key generation | `brew install python` |
| **LocalStack CLI** | Auto-read auth token | `brew install localstack/tap/localstack-cli` |
| **Google OAuth credentials** | User authentication | [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) |
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

### 2. Configure Google OAuth

1. [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. **Create Credentials → OAuth 2.0 Client ID** → Web application
3. Authorised redirect URI: `http://localhost:8000/api/v1/auth/google/callback`
4. Add to `.env.local`:

```
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

### 3. Start services

```bash
make dev-build    # first run (builds images)
make dev          # subsequent runs
```

| Service | URL | Purpose |
|---|---|---|
| **Frontend** | http://localhost:3000 | Next.js chat app |
| **Backend API** | http://localhost:8000 | FastAPI |
| **API Docs** | http://localhost:8000/docs | Swagger UI |
| **PostgreSQL** | localhost:5432 | Database |
| **Redis** | localhost:6379 | Task queue |
| **LocalStack** | http://localhost:4566 | AWS emulation (S3, STS, KMS) |

### 4. Run migrations + seed

```bash
make migrate    # creates platform schema + tables
make seed       # creates Loomaris Labs dev tenant
```

### 5. Log in

```bash
make login
# or: open http://localhost:8000/api/v1/auth/google
```

After OAuth, your account is created and auto-joined to **Loomaris Labs** as owner. The JWT is stored in `localStorage` as `loomaris_token`. The frontend auto-prompts for your Claude API key and AWS credentials on first login.

---

## Daily development

```bash
make dev              # start all services
make dev-build        # rebuild + start (after Dockerfile / requirements changes)
make reload-backend   # force-recreate backend only (after .env.local changes)
make logs             # tail backend logs
make migrate          # apply new migrations
make migrate-down     # roll back one migration
make seed             # re-seed test data
make shell            # bash inside backend container
make psql             # psql into PostgreSQL
make down             # stop all services
make login            # open Google login in browser
```

---

## Project structure

```
loomaris/
├── architecture-blueprint.md       # System design document
├── docker-compose.dev.yml          # Dev stack
├── docker-compose.prod.yml         # Production stack (nginx, certbot)
├── Makefile                        # All commands
├── .env.example                    # Template (copy → .env.local)
├── .env.production                 # Production env template (safe to commit — no secrets)
│
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app + CORS + router registration
│   │   ├── database.py             # Async SQLAlchemy engine + session
│   │   ├── core/
│   │   │   ├── config.py           # Pydantic settings (lru_cache)
│   │   │   └── security.py         # JWT + Fernet encryption helpers
│   │   ├── models/
│   │   │   ├── platform.py         # Organization, User, OrgMembership, CloudAccount
│   │   │   └── org.py              # App, ChatSession, ChatTurn, Deployment
│   │   ├── api/
│   │   │   ├── deps.py             # get_current_user dependency
│   │   │   └── routes/
│   │   │       ├── auth.py         # Google OAuth, /me, /claude-key
│   │   │       ├── apps.py         # Apps CRUD, files/git, deploy SSE, cost estimate
│   │   │       ├── chat.py         # Chat sessions + streaming generation
│   │   │       ├── cloud.py        # AWS account connect/list/delete/verify
│   │   │       └── health.py       # /health, /health/db
│   │   └── services/
│   │       ├── auth_service.py     # User create/login, API key storage
│   │       ├── tenant_service.py   # Org schema provisioning (DDL per org)
│   │       ├── chat_service.py     # Stream chat, git commit, session title generation
│   │       ├── git_service.py      # Per-app git repos, commit, zip archive
│   │       ├── deploy_service.py   # Docker-outside-of-Docker local preview deploy
│   │       └── cloud_service.py    # AWS STS validation, encrypted credential storage
│   ├── alembic/versions/
│   │   ├── 001_initial_platform_schema.py
│   │   └── 002_cloud_account_credentials.py
│   ├── scripts/
│   │   └── seed_tenant.py          # Seed Loomaris Labs dev tenant
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # Landing page (typewriter demo, features)
│   │   │   ├── login/page.tsx      # Google sign-in page
│   │   │   ├── auth/callback/page.tsx  # OAuth callback handler
│   │   │   └── chat/
│   │   │       ├── layout.tsx      # Auth guard, Claude key modal, cloud modal
│   │   │       ├── page.tsx        # /chat home (create session + redirect)
│   │   │       └── [sessionId]/page.tsx  # Chat + code panel + deploy panel
│   │   ├── components/
│   │   │   ├── Sidebar.tsx         # Session list, cloud account status
│   │   │   ├── ChatInput.tsx       # Auto-resizing textarea, Enter-to-send
│   │   │   ├── MessageBubble.tsx   # Chat message rendering (markdown)
│   │   │   ├── CodePanel.tsx       # File tabs, syntax display, download
│   │   │   ├── DeployPanel.tsx     # Deploy SSE stream, cost estimate, live link
│   │   │   ├── ApiKeyModal.tsx     # Claude API key setup modal
│   │   │   └── CloudConnectModal.tsx  # AWS credential connect modal (STS validated)
│   │   └── lib/
│   │       ├── api.ts              # All API client functions + TypeScript types
│   │       ├── auth.ts             # localStorage JWT helpers
│   │       └── stream.ts           # fetch-based SSE async generator
│   ├── Dockerfile                  # Dev
│   └── Dockerfile.prod             # Multi-stage production build
│
└── infrastructure/
    ├── nginx/
    │   ├── nginx.conf              # Main nginx config (gzip, 50m body limit)
    │   └── conf.d/loomaris.conf    # app.loomaris.xyz + api.loomaris.xyz vhosts
    ├── certbot/
    │   └── init-letsencrypt.sh     # Bootstrap Let's Encrypt (run once on fresh server)
    └── localstack/
        └── init-aws.sh             # Creates S3 buckets + KMS key on LocalStack start
```

---

## API reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/health` | — | Service health |
| `GET` | `/api/v1/health/db` | — | DB connectivity |
| `GET` | `/api/v1/auth/google` | — | Initiate Google OAuth |
| `GET` | `/api/v1/auth/google/callback` | — | OAuth callback |
| `GET` | `/api/v1/auth/me` | Bearer | Current user + org + flags |
| `POST` | `/api/v1/auth/claude-key` | Bearer | Store Anthropic key (encrypted) |
| `GET` | `/api/v1/auth/claude-key/status` | Bearer | Check if Claude key is set |
| `GET` | `/api/v1/apps` | Bearer | List apps |
| `POST` | `/api/v1/apps` | Bearer | Create app |
| `GET` | `/api/v1/apps/{id}` | Bearer | Get app |
| `GET` | `/api/v1/apps/{id}/files` | Bearer | Current files from git |
| `GET` | `/api/v1/apps/{id}/archive` | Bearer | Download zip |
| `GET` | `/api/v1/apps/{id}/sessions` | Bearer | List sessions for app |
| `POST` | `/api/v1/apps/{id}/sessions` | Bearer | Create session for app |
| `GET` | `/api/v1/apps/{id}/deploy/status` | Bearer | Container status + last deployment |
| `POST` | `/api/v1/apps/{id}/deploy` | Bearer | Deploy (SSE stream) |
| `GET` | `/api/v1/apps/{id}/cost-estimate` | Bearer | Pricing tiers |
| `GET` | `/api/v1/chat/sessions` | Bearer | List all chat sessions |
| `POST` | `/api/v1/chat/sessions` | Bearer | Create session |
| `GET` | `/api/v1/chat/sessions/{id}/history` | Bearer | Chat history |
| `POST` | `/api/v1/chat/sessions/{id}/message` | Bearer | Send message (SSE stream) |
| `POST` | `/api/v1/cloud/accounts` | Bearer | Connect AWS account (STS validated) |
| `GET` | `/api/v1/cloud/accounts` | Bearer | List cloud accounts |
| `DELETE` | `/api/v1/cloud/accounts/{id}` | Bearer | Remove account |
| `POST` | `/api/v1/cloud/accounts/{id}/verify` | Bearer | Re-verify credentials |

Full interactive docs: **http://localhost:8000/docs**

---

## Key environment variables

See [`.env.example`](.env.example) for the full list.

| Variable | Required | Auto-set by | Description |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | Yes | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | — | Google OAuth client secret |
| `ANTHROPIC_API_KEY` | Recommended | — | Master Claude key (per-user keys in DB override this) |
| `LOCALSTACK_AUTH_TOKEN` | Dev only | `make setup` | LocalStack Pro auth |
| `ENCRYPTION_KEY` | Yes | `make setup` | Fernet key for encrypting secrets at rest |
| `JWT_SECRET_KEY` | Yes | `make setup` | JWT signing key |

---

## Production deployment (loomaris.xyz)

```bash
# On the server, copy and fill in .env.production → .env
cp .env.production .env
# Edit .env: add POSTGRES_PASSWORD, GOOGLE_*, ANTHROPIC_API_KEY, ENCRYPTION_KEY, JWT_SECRET_KEY

# First deploy: get SSL certs
make ssl-init

# Start full prod stack
make prod-build
make prod-migrate
make prod-seed
```

Prod services:
- `app.loomaris.xyz` → Next.js frontend (via nginx → frontend:3000)
- `api.loomaris.xyz` → FastAPI backend (via nginx → backend:8000)
- `loomaris.xyz` / `www.` → Netlify static marketing site (separate repo)

---

## Troubleshooting

**`make dev` → `docker: No such file or directory`**
Install Docker: `brew install --cask orbstack` then open OrbStack.

**`make migrate` → connection refused**
Backend isn't up yet. Run `make dev` first, wait for healthy, then migrate in a new terminal.

**`make reload-backend` not picking up new env vars**
Use `--force-recreate` (what `reload-backend` does). Do not use `restart` — `lru_cache` on Settings requires a full container recreate.

**Google OAuth → redirect_uri_mismatch**
Redirect URI in Google Console must be exactly `http://localhost:8000/api/v1/auth/google/callback`.

**`ENCRYPTION_KEY is not set`**
Run `make setup`. Or manually:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**AWS STS validation fails in cloud connect modal**
Check the IAM user has at least `sts:GetCallerIdentity` permission. That's the minimum for connection; deploy will need more.

---

## Implementation phases

| Phase | Status | Scope |
|---|---|---|
| **Phase 1 — Local MVP** | ✅ Complete | Auth, code gen, git, local Docker deploy, cloud account connect |
| **Phase 2 — Cloud Deploy** | Planned | Pulumi IaC targeting connected AWS account, real ECS/EC2 deploy |
| **Phase 3 — Multi-tenant** | Planned | Per-org schemas fully dynamic, Vault credential storage, Stripe billing |

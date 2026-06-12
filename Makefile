SHELL := /bin/bash
.PHONY: dev dev-build down logs setup migrate migrate-down seed shell psql check-docker \
        prod prod-build prod-down prod-logs prod-shell prod-migrate prod-seed ssl-init ssl-renew

# Detect Docker — support Docker Desktop, OrbStack, Colima, and Rancher Desktop
DOCKER := $(shell command -v docker 2>/dev/null \
  || ls /usr/local/bin/docker 2>/dev/null \
  || ls /opt/homebrew/bin/docker 2>/dev/null)

# Use 'docker compose' (plugin) if available, else fall back to standalone docker-compose
DOCKER_COMPOSE := $(shell if docker compose version >/dev/null 2>&1; then \
  echo "docker compose"; \
elif command -v docker-compose >/dev/null 2>&1; then \
  echo "docker-compose"; \
else \
  echo "docker compose"; \
fi)

# ─── Prerequisite: check Docker is available ──────────────────────────────────

check-docker:
	@if [ -z "$(DOCKER)" ]; then \
		echo ""; \
		echo "  ✗  Docker not found."; \
		echo ""; \
		echo "  Install one of the following (recommended: OrbStack — lighter than Docker Desktop):"; \
		echo ""; \
		echo "    OrbStack (recommended for Mac):"; \
		echo "      brew install --cask orbstack"; \
		echo "      open /Applications/OrbStack.app"; \
		echo ""; \
		echo "    Docker Desktop:"; \
		echo "      brew install --cask docker"; \
		echo "      open /Applications/Docker.app"; \
		echo ""; \
		echo "    Colima (headless):"; \
		echo "      brew install colima docker docker-compose"; \
		echo "      colima start"; \
		echo ""; \
		exit 1; \
	fi

# ─── Dev environment ──────────────────────────────────────────────────────────

dev: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml up

dev-build: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml up --build

# Use --force-recreate (not restart) so env_file changes in .env.local are picked up
reload-backend: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml up -d --force-recreate backend

down: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml down

logs: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml logs -f backend

# ─── First-time setup ─────────────────────────────────────────────────────────

setup:
	@cp -n .env.example .env.local 2>/dev/null && echo "✓ Created .env.local from template" || echo "  .env.local already exists"
	@# Auto-read LocalStack auth token: try CLI first, then ~/.localstack/auth.json
	@LSTOKEN=""; \
	if command -v localstack >/dev/null 2>&1; then \
		LSTOKEN=$$(localstack auth token 2>/dev/null); \
	fi; \
	if [ -z "$$LSTOKEN" ] && [ -f "$$HOME/.localstack/auth.json" ]; then \
		LSTOKEN=$$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('~/.localstack/auth.json')))['LOCALSTACK_AUTH_TOKEN'])" 2>/dev/null); \
	fi; \
	if [ -n "$$LSTOKEN" ]; then \
		if grep -q "LOCALSTACK_AUTH_TOKEN=" .env.local; then \
			sed -i.bak "s|LOCALSTACK_AUTH_TOKEN=.*|LOCALSTACK_AUTH_TOKEN=$$LSTOKEN|" .env.local && rm -f .env.local.bak; \
		else \
			echo "LOCALSTACK_AUTH_TOKEN=$$LSTOKEN" >> .env.local; \
		fi; \
		echo "✓ LocalStack auth token auto-stored in .env.local"; \
	else \
		echo "  LocalStack: run 'localstack auth login' then re-run make setup"; \
	fi
	@# Generate crypto keys if they're still placeholder values (stdlib only — no extra packages needed)
	@python3 -c "\
import base64, os, secrets; \
content = open('.env.local').read(); changed = False; \
if 'your-fernet-encryption-key' in content: \
    fernet_key = base64.urlsafe_b64encode(os.urandom(32)).decode(); \
    content = content.replace('your-fernet-encryption-key', fernet_key); changed = True; \
if 'change-this-to-a-random-32-char-string' in content: \
    content = content.replace('change-this-to-a-random-32-char-string', secrets.token_hex(32)); changed = True; \
open('.env.local', 'w').write(content); \
print('✓ Generated ENCRYPTION_KEY and JWT_SECRET_KEY' if changed else '  Crypto keys already set') \
"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Next steps:"
	@echo ""
	@echo "  1. Install Docker (if not done):"
	@echo "       brew install --cask orbstack   ← recommended"
	@echo "       brew install --cask docker     ← Docker Desktop"
	@echo ""
	@echo "  2. Edit .env.local — add:"
	@echo "       GOOGLE_CLIENT_ID=..."
	@echo "       GOOGLE_CLIENT_SECRET=..."
	@echo "       ANTHROPIC_API_KEY=sk-ant-..."
	@echo "     Google credentials: https://console.cloud.google.com/apis/credentials"
	@echo "     Redirect URI to register: http://localhost:8000/api/v1/auth/google/callback"
	@echo ""
	@echo "  3. make dev-build    → build images + start all services"
	@echo "  4. make migrate      → run DB migrations"
	@echo "  5. make seed         → create Loomaris Labs test tenant"
	@echo "  6. make login        → open Google login in browser"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── Database ─────────────────────────────────────────────────────────────────

migrate: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend alembic upgrade head

migrate-down: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend alembic downgrade -1

seed: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend python scripts/seed_tenant.py

# ─── Utilities ────────────────────────────────────────────────────────────────

shell: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend bash

psql: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec postgres psql -U loomaris -d loomaris

login:
	@open http://localhost:8000/api/v1/auth/google 2>/dev/null \
	  || xdg-open http://localhost:8000/api/v1/auth/google 2>/dev/null \
	  || echo "Open: http://localhost:8000/api/v1/auth/google"

# ─── Production (loomaris.xyz) ────────────────────────────────────────────────

prod: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml up -d

prod-build: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml up -d --build

prod-down: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml down

prod-logs: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml logs -f backend nginx

prod-shell: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml exec backend bash

prod-migrate: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml exec backend alembic upgrade head

prod-seed: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml exec backend python scripts/seed_tenant.py

# Get initial SSL certificates (run once on a fresh server after DNS is pointed)
# Use --staging flag for dry-run: make ssl-init ARGS="--staging"
ssl-init: check-docker
	@bash infrastructure/certbot/init-letsencrypt.sh $(ARGS)

# Force-renew certificates now (normally handled automatically by the certbot container)
ssl-renew: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml run --rm certbot renew --force-renewal
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml exec nginx nginx -s reload

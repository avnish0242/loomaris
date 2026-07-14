SHELL := /bin/bash
.PHONY: dev dev-build down logs setup migrate migrate-down seed shell psql check-docker \
        prod prod-build prod-down prod-logs prod-shell prod-migrate prod-seed ssl-init ssl-renew \
        tf-bootstrap tf-init tf-plan tf-apply tf-destroy \
        ecr-login ecr-push ecs-migrate ecs-seed ecs-status _ecs-run-task \
        poetry-lock poetry-add poetry-update lint

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

reload-frontend: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml up -d --force-recreate frontend

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

seed-superadmin: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend python scripts/seed_superadmin.py

# ─── Poetry ───────────────────────────────────────────────────────────────────

# Regenerate poetry.lock inside the running container (after editing pyproject.toml)
poetry-lock: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend poetry lock

# Add a package: make poetry-add PKG=httpx
poetry-add: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend poetry add $(PKG)
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend poetry export -f requirements.txt --without-hashes -o /dev/null

# Update all packages to latest allowed by pyproject.toml
poetry-update: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend poetry update

# Run ruff linter inside the container
lint: check-docker
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec backend poetry run ruff check .

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

# ─── AWS / Terraform ──────────────────────────────────────────────────────────

AWS_REGION    ?= us-east-1
AWS_ACCOUNT_ID = $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null)
ECR_REGISTRY   = $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
IMAGE_TAG     ?= latest

# Bootstrap the S3 + DynamoDB Terraform state backend (run once before tf-init)
tf-bootstrap:
	@echo "Creating Terraform state backend resources..."
	aws s3api create-bucket --bucket loomaris-tf-state --region $(AWS_REGION)
	aws s3api put-bucket-versioning --bucket loomaris-tf-state \
	  --versioning-configuration Status=Enabled
	aws s3api put-bucket-encryption --bucket loomaris-tf-state \
	  --server-side-encryption-configuration \
	  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
	aws dynamodb create-table --table-name loomaris-tf-locks \
	  --attribute-definitions AttributeName=LockID,AttributeType=S \
	  --key-schema AttributeName=LockID,KeyType=HASH \
	  --billing-mode PAY_PER_REQUEST --region $(AWS_REGION)
	@echo "Bootstrap complete. Now run: make tf-init"

tf-init:
	terraform -chdir=infrastructure/terraform init

tf-plan:
	terraform -chdir=infrastructure/terraform plan

tf-apply:
	terraform -chdir=infrastructure/terraform apply

tf-destroy:
	@echo "WARNING: This will destroy all production infrastructure. Type 'yes' to confirm:"
	@read ans && [ "$$ans" = "yes" ] || (echo "Aborted." && exit 1)
	terraform -chdir=infrastructure/terraform destroy

# ─── ECR ──────────────────────────────────────────────────────────────────────

ecr-login:
	aws ecr get-login-password --region $(AWS_REGION) | \
	  docker login --username AWS --password-stdin $(ECR_REGISTRY)

ecr-push: check-docker ecr-login
	@echo "→ Building and pushing backend (tag: $(IMAGE_TAG))..."
	docker build --platform linux/amd64 -t $(ECR_REGISTRY)/loomaris/backend:$(IMAGE_TAG) ./backend
	docker push $(ECR_REGISTRY)/loomaris/backend:$(IMAGE_TAG)
	@echo "→ Building and pushing frontend (tag: $(IMAGE_TAG))..."
	docker build \
	  --platform linux/amd64 \
	  --file ./frontend/Dockerfile.prod \
	  --build-arg NEXT_PUBLIC_API_URL=https://api.loomaris.xyz \
	  -t $(ECR_REGISTRY)/loomaris/frontend:$(IMAGE_TAG) \
	  ./frontend
	docker push $(ECR_REGISTRY)/loomaris/frontend:$(IMAGE_TAG)
	@echo "Images pushed. Run 'make tf-apply' to update ECS task definitions."

# ─── ECS one-off tasks ────────────────────────────────────────────────────────

ecs-migrate:
	@$(MAKE) _ecs-run-task TASK=backend CMD='["alembic","upgrade","head"]'

ecs-seed:
	@$(MAKE) _ecs-run-task TASK=backend CMD='["python","scripts/seed_tenant.py"]'

_ecs-run-task:
	$(eval SUBNETS := $(shell aws ec2 describe-subnets \
	  --filters "Name=tag:Name,Values=loomaris-public-*" \
	  --query 'Subnets[].SubnetId' --output text | tr '\t' ','))
	$(eval SG := $(shell aws ec2 describe-security-groups \
	  --filters "Name=group-name,Values=loomaris-ecs" \
	  --query 'SecurityGroups[0].GroupId' --output text))
	$(eval TASK_DEF := $(shell aws ecs describe-task-definition \
	  --task-definition loomaris-$(TASK) \
	  --query 'taskDefinition.taskDefinitionArn' --output text))
	@aws ecs run-task \
	  --cluster loomaris \
	  --task-definition $(TASK_DEF) \
	  --launch-type FARGATE \
	  --network-configuration \
	    "awsvpcConfiguration={subnets=[$(SUBNETS)],securityGroups=[$(SG)],assignPublicIp=ENABLED}" \
	  --overrides \
	    '{"containerOverrides":[{"name":"$(TASK)","command":$(CMD)}]}' \
	  --query 'tasks[0].taskArn' --output text

ecs-status:
	@echo "=== Backend ==="
	@aws ecs describe-services --cluster loomaris --services loomaris-backend \
	  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,Pending:pendingCount}' \
	  --output table
	@echo "=== Frontend ==="
	@aws ecs describe-services --cluster loomaris --services loomaris-frontend \
	  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,Pending:pendingCount}' \
	  --output table

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_ENV: str = "development"
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    DOMAIN: str = "loomaris.xyz"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://loomaris:loomaris@localhost:5432/loomaris"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"


    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # GitHub OAuth
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/github/callback"

    # Zoho OAuth
    ZOHO_CLIENT_ID: str = ""
    ZOHO_CLIENT_SECRET: str = ""
    ZOHO_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/zoho/callback"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Encryption key (Fernet) for sensitive values stored in DB
    ENCRYPTION_KEY: str = ""

    # Anthropic — master key (Phase 1 fallback; per-user keys stored encrypted in DB)
    ANTHROPIC_API_KEY: str = ""

    # AWS / LocalStack
    AWS_ENDPOINT_URL: str = ""        # empty = real AWS; set to http://localhost:4566 for LocalStack
    AWS_ACCESS_KEY_ID: str = "test"
    AWS_SECRET_ACCESS_KEY: str = "test"
    AWS_DEFAULT_REGION: str = "us-east-1"

    # LocalStack
    LOCALSTACK_AUTH_TOKEN: str = ""

    # Loomaris control-plane IAM user (used for STS cross-account assume-role)
    # Create arn:aws:iam::LOOMARIS_ACCT:user/loomaris-deployer and paste creds here.
    LOOMARIS_DEPLOYER_ACCESS_KEY: str = ""
    LOOMARIS_DEPLOYER_SECRET_KEY: str = ""

    # S3 bucket for persistent Pulumi state (required for pulumi destroy to work)
    # e.g. "loomaris-pulumi-state"
    PULUMI_STATE_BUCKET: str = ""

    # Loomaris AWS account ID (shown in trust policy templates to orgs)
    LOOMARIS_AWS_ACCOUNT_ID: str = ""

    # Ephemeral simulation infra (ECS Fargate in dedicated Loomaris sim AWS account)
    SIM_ECS_CLUSTER: str = ""           # arn:aws:ecs:us-east-1:ACCT:cluster/loomaris-sim
    SIM_ECR_BASE_URI: str = ""          # ACCT.dkr.ecr.us-east-1.amazonaws.com/loomaris-previews
    SIM_SUBNET_ID: str = ""             # public subnet in Loomaris sim VPC
    SIM_SECURITY_GROUP_ID: str = ""     # allows inbound on app port, outbound all
    SIM_TASK_EXECUTION_ROLE: str = ""   # arn:aws:iam::ACCT:role/loomaris-sim-exec
    SIM_TEARDOWN_LAMBDA_ARN: str = ""   # for EventBridge Scheduler target

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def using_localstack(self) -> bool:
        return bool(self.AWS_ENDPOINT_URL)

    @property
    def cors_origins(self) -> list[str]:
        origins = {"http://localhost:3000", "http://localhost:8000", self.FRONTEND_URL}
        if not self.is_dev:
            origins |= {
                f"https://{self.DOMAIN}",
                f"https://www.{self.DOMAIN}",
                f"https://api.{self.DOMAIN}",
            }
        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

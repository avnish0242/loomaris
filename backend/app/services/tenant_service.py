import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import CloudAccount, OrgMembership, Organization

# DDL template for per-org schema tables — {schema} and {schema_raw} are substituted at runtime
_ORG_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.apps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    app_type VARCHAR(50) NOT NULL DEFAULT 'web',
    git_repo_url VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{{}}'
);

CREATE TABLE IF NOT EXISTS {schema}.chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id UUID REFERENCES {schema}.apps(id),
    title VARCHAR(255),
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS {schema}.chat_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES {schema}.chat_sessions(id),
    turn_index INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    git_commit_sha VARCHAR(40),
    token_count INTEGER,
    scan_result JSONB,
    pending_tool_use_id TEXT,
    pending_tool_name TEXT,
    pending_tool_input JSONB,
    tool_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS {schema}.deployments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id UUID NOT NULL REFERENCES {schema}.apps(id),
    turn_id UUID REFERENCES {schema}.chat_turns(id),
    cloud_account_id UUID,
    environment VARCHAR(50) NOT NULL DEFAULT 'preview',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    pulumi_stack_id VARCHAR(255),
    outputs JSONB,
    cost_snapshot JSONB,
    commit_sha VARCHAR(40),
    bypassed_simulation_gate BOOLEAN NOT NULL DEFAULT FALSE,
    cloud_provider VARCHAR(20),
    deployed_at TIMESTAMPTZ,
    destroyed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS {schema}.cost_estimates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id UUID NOT NULL REFERENCES {schema}.apps(id),
    turn_id UUID,
    cloud_provider VARCHAR(20),
    tier_matrix JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS {schema}.audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    user_id UUID,
    resource_type VARCHAR(50),
    resource_id UUID,
    details JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_{schema_raw}_audit_log
    ON {schema}.audit_log (event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS {schema}.simulation_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id UUID NOT NULL REFERENCES {schema}.apps(id),
    user_id UUID NOT NULL,
    task_arn VARCHAR(500),
    image_uri VARCHAR(500),
    public_ip VARCHAR(50),
    url VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'building',
    ttl_seconds INTEGER NOT NULL DEFAULT 600,
    expires_at TIMESTAMPTZ,
    cost_usd NUMERIC(8,6),
    commit_sha VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_{schema_raw}_sim_sessions_app
    ON {schema}.simulation_sessions (app_id, created_at DESC);
"""


def _schema_name(org_slug: str) -> str:
    return "org_" + org_slug.replace("-", "_")


async def create_org_schema(db: AsyncSession, org_slug: str) -> str:
    schema = _schema_name(org_slug)
    await db.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

    # asyncpg rejects multi-statement strings in a single execute() call —
    # split on blank lines and run each CREATE statement separately.
    ddl = _ORG_SCHEMA_DDL.format(schema=schema, schema_raw=schema)
    statements = [s.strip() for s in ddl.split("\n\n") if s.strip()]
    for stmt in statements:
        await db.execute(text(stmt))

    await db.commit()
    return schema


async def get_or_create_default_org(db: AsyncSession) -> Organization:
    """Phase 1: single org. Returns or creates the Loomaris Labs dev tenant."""
    result = await db.execute(
        select(Organization).where(Organization.slug == "loomaris-labs")
    )
    org = result.scalar_one_or_none()
    if not org:
        org = Organization(
            name="Loomaris Labs",
            slug="loomaris-labs",
            plan="pro",
            cost_hard_cap=10000.00,
            metadata_={"env": "dev", "description": "Internal development tenant"},
        )
        db.add(org)
        await db.flush()
        await create_org_schema(db, org.slug)

        cloud_account = CloudAccount(
            org_id=org.id,
            provider="aws",
            display_name="LocalStack Dev (AWS)",
            external_id="000000000000",
            vault_path="dev/localstack",
            status="verified",
        )
        db.add(cloud_account)
        await db.commit()

    return org


async def add_user_to_org(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    role: str = "owner",
    status: str = "active",
) -> OrgMembership:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        membership = OrgMembership(org_id=org_id, user_id=user_id, role=role, status=status)
        db.add(membership)
        await db.commit()
    return membership

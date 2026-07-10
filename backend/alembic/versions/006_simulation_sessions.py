"""Add simulation_sessions per-org table and platform.simulation_budget_log.

Revision ID: 006
Revises: 005
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Platform-level budget log (cross-org, per-user spend tracking)
    op.create_table(
        "simulation_budget_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("simulation_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cost_usd", sa.Numeric(8, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()")),
        schema="platform",
    )
    op.create_index(
        "idx_sim_budget_log_user", "simulation_budget_log",
        ["user_id", "created_at"], schema="platform",
    )

    # 2. Add simulation_sessions to every existing org schema
    result = conn.execute(
        text("SELECT slug FROM platform.organizations WHERE suspended_at IS NULL")
    )
    slugs = [row[0] for row in result]

    for slug in slugs:
        schema = "org_" + slug.replace("-", "_")
        schema_raw = schema

        # Verify the schema exists before trying to add a table
        exists = conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
            {"s": schema},
        ).scalar()
        if not exists:
            continue

        conn.execute(text(f"""
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
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_raw}_sim_sessions_app
                ON {schema}.simulation_sessions (app_id, created_at DESC)
        """))


def downgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(
        text("SELECT slug FROM platform.organizations")
    )
    for (slug,) in result:
        schema = "org_" + slug.replace("-", "_")
        conn.execute(text(f"DROP TABLE IF EXISTS {schema}.simulation_sessions CASCADE"))

    op.drop_index("idx_sim_budget_log_user", "simulation_budget_log", schema="platform")
    op.drop_table("simulation_budget_log", schema="platform")

"""Initial platform schema

Revision ID: 001
Revises:
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions and schema
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")

    # ── organizations ─────────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="trial"),
        sa.Column("cost_hard_cap", sa.Numeric(12, 2), nullable=False, server_default="500.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        schema="platform",
    )
    op.create_unique_constraint(
        "uq_organizations_slug", "organizations", ["slug"], schema="platform"
    )

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("picture", sa.String(1000), nullable=True),
        sa.Column("google_sub", sa.String(255), nullable=True),
        sa.Column("google_refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("anthropic_api_key_enc", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        schema="platform",
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"], schema="platform")
    op.create_unique_constraint(
        "uq_users_google_sub", "users", ["google_sub"], schema="platform"
    )

    # ── org_memberships ───────────────────────────────────────────────────────
    op.create_table(
        "org_memberships",
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="platform",
    )

    # ── cloud_accounts ────────────────────────────────────────────────────────
    op.create_table(
        "cloud_accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.organizations.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("vault_path", sa.String(500), nullable=False),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="pending_verification",
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="platform",
    )



def downgrade() -> None:
    op.drop_table("cloud_accounts", schema="platform")
    op.drop_table("org_memberships", schema="platform")
    op.drop_table("users", schema="platform")
    op.drop_table("organizations", schema="platform")
    op.execute("DROP TABLE IF EXISTS platform.alembic_version")
    op.execute("DROP SCHEMA IF EXISTS platform CASCADE")

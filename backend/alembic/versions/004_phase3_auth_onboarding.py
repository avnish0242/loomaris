"""Phase 3: multi-tenant auth, GitHub OAuth, org-level API key, onboarding flow

Revision ID: 004
Revises: 003
Create Date: 2026-06-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users: add github_sub + is_superadmin ─────────────────────────────────
    op.add_column(
        "users",
        sa.Column("github_sub", sa.String(255), nullable=True),
        schema="platform",
    )
    op.create_unique_constraint(
        "uq_users_github_sub", "users", ["github_sub"], schema="platform"
    )
    op.add_column(
        "users",
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default="false"),
        schema="platform",
    )
    # Drop the per-user anthropic key column (moved to orgs)
    op.drop_column("users", "anthropic_api_key_enc", schema="platform")

    # ── organizations: add new fields ─────────────────────────────────────────
    op.add_column(
        "organizations",
        sa.Column("anthropic_api_key_enc", sa.Text(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "organizations",
        sa.Column("description", sa.String(500), nullable=True),
        schema="platform",
    )
    op.add_column(
        "organizations",
        sa.Column(
            "join_policy",
            sa.String(50),
            nullable=False,
            server_default="approval_required",
        ),
        schema="platform",
    )

    # ── org_memberships: add status ───────────────────────────────────────────
    op.add_column(
        "org_memberships",
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        schema="platform",
    )
    op.create_index(
        "idx_org_memberships_status",
        "org_memberships",
        ["status"],
        schema="platform",
    )

    # ── org_invites: new table ────────────────────────────────────────────────
    op.create_table(
        "org_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invited_email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("token", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )
    op.create_index(
        "idx_org_invites_token", "org_invites", ["token"], schema="platform"
    )
    op.create_index(
        "idx_org_invites_email", "org_invites", ["invited_email"], schema="platform"
    )


def downgrade() -> None:
    op.drop_table("org_invites", schema="platform")
    op.drop_index("idx_org_memberships_status", "org_memberships", schema="platform")
    op.drop_column("org_memberships", "status", schema="platform")
    op.drop_column("organizations", "join_policy", schema="platform")
    op.drop_column("organizations", "description", schema="platform")
    op.drop_column("organizations", "anthropic_api_key_enc", schema="platform")
    op.add_column(
        "users",
        sa.Column("anthropic_api_key_enc", sa.Text(), nullable=True),
        schema="platform",
    )
    op.drop_constraint("uq_users_github_sub", "users", schema="platform", type_="unique")
    op.drop_column("users", "github_sub", schema="platform")
    op.drop_column("users", "is_superadmin", schema="platform")

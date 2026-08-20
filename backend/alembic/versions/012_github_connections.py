"""Add platform.github_connections — org-level GitHub App installations.

One row per org's active GitHub App installation (export/push credential),
distinct from users.github_sub (login identity). Platform-schema table, not
per-org — same tier as cloud_accounts, no org-schema loop needed.

Revision ID: 012
Revises: 011
Create Date: 2026-08-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("platform.organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column("connected_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        schema="platform",
    )
    op.create_index(
        "idx_github_connections_org", "github_connections", ["org_id"], schema="platform",
    )


def downgrade() -> None:
    op.drop_index("idx_github_connections_org", "github_connections", schema="platform")
    op.drop_table("github_connections", schema="platform")

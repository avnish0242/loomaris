"""STS cross-account role: add role_arn, sts_external_id, connection_type to cloud_accounts.
Mark existing key-based accounts as reconnect_required.

Revision ID: 005
Revises: 004
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cloud_accounts",
        sa.Column("connection_type", sa.String(20), nullable=False, server_default="keys"),
        schema="platform",
    )
    op.add_column(
        "cloud_accounts",
        sa.Column("role_arn", sa.String(500), nullable=True),
        schema="platform",
    )
    op.add_column(
        "cloud_accounts",
        sa.Column("sts_external_id", sa.String(255), nullable=True),
        schema="platform",
    )

    # Hard migration: mark all existing key-based accounts as needing reconnection via STS role.
    op.execute(
        """
        UPDATE platform.cloud_accounts
        SET connection_type = 'keys',
            status = 'reconnect_required'
        WHERE access_key_enc IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("cloud_accounts", "sts_external_id", schema="platform")
    op.drop_column("cloud_accounts", "role_arn", schema="platform")
    op.drop_column("cloud_accounts", "connection_type", schema="platform")

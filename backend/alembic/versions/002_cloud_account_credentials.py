"""Add credential columns to cloud_accounts

Revision ID: 002
Revises: 001
Create Date: 2026-06-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cloud_accounts",
        sa.Column("access_key_enc", sa.Text(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "cloud_accounts",
        sa.Column("secret_key_enc", sa.Text(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "cloud_accounts",
        sa.Column("region", sa.String(50), nullable=True, server_default="us-east-1"),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_column("cloud_accounts", "region", schema="platform")
    op.drop_column("cloud_accounts", "secret_key_enc", schema="platform")
    op.drop_column("cloud_accounts", "access_key_enc", schema="platform")

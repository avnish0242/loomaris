"""Add zoho_sub column to platform.users for Zoho OAuth.

Revision ID: 008
Revises: 007
Create Date: 2026-07-14
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(text("""
        ALTER TABLE platform.users
        ADD COLUMN IF NOT EXISTS zoho_sub VARCHAR(255) UNIQUE
    """))


def downgrade() -> None:
    op.get_bind().execute(text("""
        ALTER TABLE platform.users
        DROP COLUMN IF EXISTS zoho_sub
    """))

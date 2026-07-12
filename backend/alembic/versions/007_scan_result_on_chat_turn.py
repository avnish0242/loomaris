"""Add scan_result JSONB column to per-org chat_turns tables.

Revision ID: 007
Revises: 006
Create Date: 2026-07-13
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(
        text("SELECT slug FROM platform.organizations WHERE suspended_at IS NULL")
    )
    slugs = [row[0] for row in result]

    for slug in slugs:
        schema = "org_" + slug.replace("-", "_")

        exists = conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
            {"s": schema},
        ).scalar()
        if not exists:
            continue

        conn.execute(text(f"""
            ALTER TABLE {schema}.chat_turns
            ADD COLUMN IF NOT EXISTS scan_result JSONB
        """))


def downgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(
        text("SELECT slug FROM platform.organizations")
    )
    for (slug,) in result:
        schema = "org_" + slug.replace("-", "_")
        conn.execute(text(f"""
            ALTER TABLE {schema}.chat_turns
            DROP COLUMN IF EXISTS scan_result
        """))

"""Backfill scan_result column into per-org chat_turns tables missed by 007.

Migration 007 only backfilled orgs that existed in platform.organizations at
the time it ran. tenant_service.py's CREATE TABLE template was never updated
to include scan_result, so any org schema created after 007 (e.g. via the
org creation flow) has been missing the column ever since — this backfills
those, and is a no-op for schemas that already have it.

Revision ID: 009
Revises: 008
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "009"
down_revision: Union[str, None] = "008"
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

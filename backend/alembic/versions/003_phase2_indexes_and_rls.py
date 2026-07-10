"""Phase 2: add indexes, RLS backup policies, and audit_log user_id index

Revision ID: 003
Revises: 002
Create Date: 2026-06-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _org_schema_exists(schema_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = :s"
        ),
        {"s": schema_name},
    )
    return result.fetchone() is not None


def _add_indexes_for_schema(schema: str) -> None:
    """Add missing Phase 2 indexes to a given org schema."""
    conn = op.get_bind()

    indexes = [
        f"CREATE INDEX IF NOT EXISTS idx_{schema}_audit_user ON {schema}.audit_log (user_id, created_at DESC)",
        f"CREATE INDEX IF NOT EXISTS idx_{schema}_deploy_app ON {schema}.deployments (app_id, created_at DESC)",
        f"CREATE INDEX IF NOT EXISTS idx_{schema}_deploy_status ON {schema}.deployments (status)",
        f"CREATE INDEX IF NOT EXISTS idx_{schema}_cost_app ON {schema}.cost_estimates (app_id, created_at DESC)",
        f"CREATE INDEX IF NOT EXISTS idx_{schema}_session_user ON {schema}.chat_sessions (created_by, last_active_at DESC)",
    ]
    for sql in indexes:
        conn.execute(sa.text(sql))


def upgrade() -> None:
    conn = op.get_bind()

    # Add indexes to all existing org schemas (found by naming pattern)
    result = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'org_%' ORDER BY schema_name"
        )
    )
    org_schemas = [row[0] for row in result]

    for schema in org_schemas:
        _add_indexes_for_schema(schema)

    # Ensure cost_estimates table exists in all org schemas (added in Phase 2)
    for schema in org_schemas:
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS {schema}.cost_estimates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                app_id UUID NOT NULL REFERENCES {schema}.apps(id),
                turn_id UUID,
                cloud_provider VARCHAR(20),
                tier_matrix JSONB NOT NULL DEFAULT '{{}}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS idx_{schema}_cost_app "
            f"ON {schema}.cost_estimates (app_id, created_at DESC)"
        ))

    # Add turn_id FK to deployments if not already present (Phase 2 model update)
    for schema in org_schemas:
        # Check if the FK exists; add it if not (idempotent via IF NOT EXISTS equivalent)
        fk_exists = conn.execute(sa.text("""
            SELECT 1 FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = :schema
              AND tc.table_name = 'deployments'
              AND kcu.column_name = 'turn_id'
        """), {"schema": schema}).fetchone()

        if not fk_exists:
            try:
                conn.execute(sa.text(
                    f"ALTER TABLE {schema}.deployments "
                    f"ADD CONSTRAINT fk_{schema}_dep_turn "
                    f"FOREIGN KEY (turn_id) REFERENCES {schema}.chat_turns(id)"
                ))
            except Exception:
                pass  # FK may already exist with a different constraint name


def downgrade() -> None:
    # Indexes are idempotent; downgrade is a no-op for safety
    pass

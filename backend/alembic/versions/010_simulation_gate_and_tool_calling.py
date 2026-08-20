"""Add simulation-gate and chat-tool-calling columns to per-org tables.

Adds:
- chat_turns: pending_tool_use_id, pending_tool_name, pending_tool_input, tool_status
  (persists an unconfirmed chat tool call between the SSE stream ending and the
  user clicking Confirm/Deny)
- simulation_sessions: commit_sha (real git HEAD sha at simulation launch, used by
  the deploy gate — distinct from sim_service's unrelated content-hash "commit_sha")
- deployments: commit_sha, bypassed_simulation_gate, cloud_provider

tenant_service.py's _ORG_SCHEMA_DDL is updated alongside this migration so newly
created orgs get these columns immediately (see migration 009's docstring for what
happens when that step is skipped).

Revision ID: 010
Revises: 009
Create Date: 2026-08-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ADD_COLUMNS = """
ALTER TABLE {schema}.chat_turns
    ADD COLUMN IF NOT EXISTS pending_tool_use_id TEXT,
    ADD COLUMN IF NOT EXISTS pending_tool_name TEXT,
    ADD COLUMN IF NOT EXISTS pending_tool_input JSONB,
    ADD COLUMN IF NOT EXISTS tool_status TEXT;

ALTER TABLE {schema}.simulation_sessions
    ADD COLUMN IF NOT EXISTS commit_sha VARCHAR(40);

ALTER TABLE {schema}.deployments
    ADD COLUMN IF NOT EXISTS commit_sha VARCHAR(40),
    ADD COLUMN IF NOT EXISTS bypassed_simulation_gate BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cloud_provider VARCHAR(20);
"""

_DROP_COLUMNS = """
ALTER TABLE {schema}.deployments
    DROP COLUMN IF EXISTS cloud_provider,
    DROP COLUMN IF EXISTS bypassed_simulation_gate,
    DROP COLUMN IF EXISTS commit_sha;

ALTER TABLE {schema}.simulation_sessions
    DROP COLUMN IF EXISTS commit_sha;

ALTER TABLE {schema}.chat_turns
    DROP COLUMN IF EXISTS tool_status,
    DROP COLUMN IF EXISTS pending_tool_input,
    DROP COLUMN IF EXISTS pending_tool_name,
    DROP COLUMN IF EXISTS pending_tool_use_id;
"""


def _org_schemas(conn, *, active_only: bool) -> list[str]:
    where = "WHERE suspended_at IS NULL" if active_only else ""
    result = conn.execute(text(f"SELECT slug FROM platform.organizations {where}"))
    slugs = [row[0] for row in result]

    schemas = []
    for slug in slugs:
        schema = "org_" + slug.replace("-", "_")
        exists = conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
            {"s": schema},
        ).scalar()
        if exists:
            schemas.append(schema)
    return schemas


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _org_schemas(conn, active_only=True):
        for stmt in _ADD_COLUMNS.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt.format(schema=schema)))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _org_schemas(conn, active_only=False):
        for stmt in _DROP_COLUMNS.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt.format(schema=schema)))

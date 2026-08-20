"""Add generic encrypted credentials_enc JSONB-as-text column to cloud_accounts.

New Azure connections and all GCP connections write a provider-shaped credentials
dict here (Fernet-encrypted, same helper as access_key_enc/secret_key_enc). Existing
AWS rows and legacy Azure rows (which store client_id/client_secret/tenant_id in the
AWS-named columns) are left untouched — cloud_service.get_credentials() reads this
column first and falls back to the legacy columns when it's null, so no live secrets
need to be migrated.

Revision ID: 011
Revises: 010
Create Date: 2026-08-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cloud_accounts",
        sa.Column("credentials_enc", sa.Text(), nullable=True),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_column("cloud_accounts", "credentials_enc", schema="platform")

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="trial")
    cost_hard_cap: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=500.00)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    memberships: Mapped[list["OrgMembership"]] = relationship(back_populates="organization")
    cloud_accounts: Mapped[list["CloudAccount"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    picture: Mapped[str | None] = mapped_column(String(1000))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    google_refresh_token_enc: Mapped[str | None] = mapped_column(Text)  # Fernet encrypted
    anthropic_api_key_enc: Mapped[str | None] = mapped_column(Text)     # Fernet encrypted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["OrgMembership"]] = relationship(back_populates="user")


class OrgMembership(Base):
    __tablename__ = "org_memberships"
    __table_args__ = {"schema": "platform"}

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class CloudAccount(Base):
    __tablename__ = "cloud_accounts"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.organizations.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)         # aws | azure | gcp
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)     # AWS account ID / etc.
    vault_path: Mapped[str] = mapped_column(String(500), nullable=False)      # Vault KV path (Phase 3)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending_verification")
    access_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)   # Fernet encrypted
    secret_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)   # Fernet encrypted
    region: Mapped[str | None] = mapped_column(String(50), nullable=True, default="us-east-1")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="cloud_accounts")

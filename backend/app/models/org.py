import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# Phase 1: single-org — schema is fixed. Phase 2 will make this dynamic per request.
_SCHEMA = "org_loomaris_labs"


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = {"schema": _SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id = Column(UUID(as_uuid=True), ForeignKey(f"{_SCHEMA}.apps.id"), nullable=False)
    turn_id = Column(UUID(as_uuid=True), nullable=True)
    cloud_account_id = Column(UUID(as_uuid=True), nullable=True)
    environment = Column(String(50), nullable=False, default="preview")
    status = Column(String(50), nullable=False, default="pending")
    pulumi_stack_id = Column(String(255), nullable=True)
    outputs = Column(JSONB, nullable=True)        # {url, port, container_id, image_tag}
    cost_snapshot = Column(JSONB, nullable=True)
    deployed_at = Column(DateTime(timezone=True), nullable=True)
    destroyed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    app = relationship("App", back_populates="deployments")


class App(Base):
    __tablename__ = "apps"
    __table_args__ = {"schema": _SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False)
    app_type = Column(String(50), nullable=False, server_default="web")
    git_repo_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")

    sessions = relationship("ChatSession", back_populates="app", lazy="select")
    deployments = relationship("Deployment", back_populates="app", lazy="select")


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = {"schema": _SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id = Column(UUID(as_uuid=True), ForeignKey(f"{_SCHEMA}.apps.id"), nullable=True)
    title = Column(String(255), nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), server_default=func.now())

    app = relationship("App", back_populates="sessions")
    turns = relationship("ChatTurn", back_populates="session", order_by="ChatTurn.turn_index")


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = {"schema": _SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.chat_sessions.id"),
        nullable=False,
    )
    turn_index = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    git_commit_sha = Column(String(40), nullable=True)
    token_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="turns")

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import TenantContext, get_tenant_context
from app.models.org import ChatSession, ChatTurn
from app.services.auth_service import get_anthropic_key  # now reads from org
from app.services.chat_service import (
    create_session,
    get_session_history,
    resume_after_tool_confirmation,
    stream_chat,
)
from app.services.guardrail_service import GuardrailAction, classify_message

router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SendMessageRequest(BaseModel):
    message: str


class ToolConfirmationRequest(BaseModel):
    turn_id: uuid.UUID
    tool_use_id: str
    decision: Literal["approve", "deny"]
    cloud_account_id: uuid.UUID | None = None
    deploy_without_preview: bool = False


def _session_out(s: ChatSession) -> dict:
    return {
        "id": str(s.id),
        "app_id": str(s.app_id) if s.app_id else None,
        "title": s.title,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
    }


def _turn_out(t: ChatTurn) -> dict:
    return {
        "id": str(t.id),
        "role": t.role,
        "content": t.content,
        "turn_index": t.turn_index,
        "token_count": t.token_count,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Create a standalone chat session (not tied to an app)",
)
async def create_chat_session(
    body: CreateSessionRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    session = await create_session(ctx.session, user_id=ctx.user.id, title=body.title)
    await ctx.session.commit()
    await ctx.session.refresh(session)
    return _session_out(session)


@router.get("/sessions", summary="List all chat sessions for the current user")
async def list_sessions(
    ctx: TenantContext = Depends(get_tenant_context),
):
    result = await ctx.session.execute(
        select(ChatSession)
        .where(ChatSession.created_by == ctx.user.id)
        .order_by(ChatSession.last_active_at.desc())
    )
    return [_session_out(s) for s in result.scalars().all()]


@router.get("/sessions/{session_id}", summary="Get a single chat session by ID")
async def get_session(
    session_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    result = await ctx.session.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.created_by == ctx.user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_out(session)


@router.post(
    "/sessions/{session_id}/message",
    summary="Send a message — returns an SSE stream of Claude's response",
)
async def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    # ── Verify session exists ─────────────────────────────────────────────────
    result = await ctx.session.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    # ── Pre-prompt guardrail ──────────────────────────────────────────────────
    api_key = await get_anthropic_key(ctx.session, ctx.org.id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No Claude API key configured. POST /api/v1/auth/claude-key first.",
        )

    decision = await classify_message(
        message=body.message,
        api_key=api_key,
        org_id=str(ctx.org.id),
        user_id=str(ctx.user.id),
        db=ctx.session,
    )

    if decision.action == GuardrailAction.BLOCK:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail={
                "error": "REQUEST_BLOCKED",
                "message": (
                    "This request was flagged by our safety system and cannot be processed. "
                    f"Category: {decision.category}. "
                    "If you believe this is a mistake, contact support."
                ),
                "category": decision.category,
                "risk_score": decision.risk_score,
            },
        )

    return StreamingResponse(
        stream_chat(ctx, session_id, body.message, api_key),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/sessions/{session_id}/tool-confirmations",
    summary="Approve or deny a pending simulate_app/deploy_app tool call — returns an SSE stream",
)
async def confirm_tool_call(
    session_id: uuid.UUID,
    body: ToolConfirmationRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    result = await ctx.session.execute(
        select(ChatTurn).where(
            ChatTurn.id == body.turn_id,
            ChatTurn.session_id == session_id,
            ChatTurn.pending_tool_use_id == body.tool_use_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="No matching pending tool call found")

    api_key = await get_anthropic_key(ctx.session, ctx.org.id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No Claude API key configured. POST /api/v1/auth/claude-key first.",
        )

    return StreamingResponse(
        resume_after_tool_confirmation(
            ctx,
            session_id,
            body.turn_id,
            body.decision,
            api_key,
            cloud_account_id=body.cloud_account_id,
            deploy_without_preview=body.deploy_without_preview,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/sessions/{session_id}/history",
    summary="Get the full message history for a session",
)
async def get_history(
    session_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    result = await ctx.session.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    turns = await get_session_history(ctx.session, session_id)
    return [_turn_out(t) for t in turns]

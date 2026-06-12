import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.org import ChatSession, ChatTurn
from app.models.platform import User
from app.services.auth_service import get_anthropic_key
from app.services.chat_service import create_session, get_session_history, stream_chat

router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SendMessageRequest(BaseModel):
    message: str


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await create_session(db, user_id=current_user.id, title=body.title)
    await db.commit()
    await db.refresh(session)
    return _session_out(session)


@router.get("/sessions", summary="List all chat sessions for the current user")
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.created_by == current_user.id)
        .order_by(ChatSession.last_active_at.desc())
    )
    return [_session_out(s) for s in result.scalars().all()]


@router.post(
    "/sessions/{session_id}/message",
    summary="Send a message — returns an SSE stream of Claude's response",
)
async def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    api_key = await get_anthropic_key(db, current_user.id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No Claude API key configured. POST /api/v1/auth/claude-key first.",
        )

    return StreamingResponse(
        stream_chat(db, session_id, body.message, api_key),
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
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    turns = await get_session_history(db, session_id)
    return [_turn_out(t) for t in turns]

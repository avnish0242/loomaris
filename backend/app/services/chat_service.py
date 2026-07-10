import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org import App, ChatSession, ChatTurn
from app.services.git_service import commit_files, extract_files, get_current_files

log = logging.getLogger(__name__)

_BASE_SYSTEM_PROMPT = """\
You are Loomaris, an expert full-stack engineer and cloud architect embedded in a \
self-orchestration platform. Users describe what they want to build in natural language \
and you generate complete, production-ready application code deployed to their own cloud.

## Code file format

When writing or modifying files use this exact format — the platform parses these blocks \
to save files, commit to git, and deploy:

```file:relative/path/to/file.ext
// file contents here
```

Always generate:
- Complete, runnable code (no "TODO" placeholders, no stub bodies)
- A Dockerfile if the app should run as a container
- requirements.txt / package.json as appropriate
- At least one sentence explaining the key architectural choice

## Behaviour guidelines

- Prefer simple, proven technology over cutting-edge
- Default web stack: Python FastAPI + HTML/JS (unless specified)
- When iterating, output ONLY the files that changed — say which ones and why
- If a request is ambiguous, ask ONE clarifying question before generating code
"""


def _build_system_prompt(existing_files: list) -> str:
    """Inject the app's current codebase into the system prompt for follow-up turns."""
    if not existing_files:
        return _BASE_SYSTEM_PROMPT

    context_lines = ["\n\n## Current codebase\n\nThe app already has these files. When the user asks to modify or extend it, update only what's necessary and output the full content of changed files.\n"]
    for f in existing_files[:12]:  # cap at 12 files to stay within context budget
        # Truncate very large files
        content = f.content if len(f.content) < 3000 else f.content[:3000] + "\n… [truncated]"
        context_lines.append(f"\n```file:{f.path}\n{content}\n```")
    return _BASE_SYSTEM_PROMPT + "".join(context_lines)


async def _generate_title(api_key: str, user_message: str, assistant_snippet: str) -> str:
    """Generate a short session title using a fast, cheap call to claude-haiku."""
    try:
        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{
                "role": "user",
                "content": (
                    f"Generate a 3-5 word title for this coding conversation.\n"
                    f"User asked: {user_message[:150]}\n"
                    f"Respond with ONLY the title, no punctuation, no quotes."
                ),
            }],
        )
        return resp.content[0].text.strip()
    except Exception:
        # Fallback: truncate the user message
        return user_message[:50]


async def get_or_create_app(db: AsyncSession, *, name: str, app_type: str = "web") -> App:
    slug = name.lower().replace(" ", "-").replace("_", "-")
    result = await db.execute(select(App).where(App.slug == slug))
    app = result.scalar_one_or_none()
    if not app:
        app = App(name=name, slug=slug, app_type=app_type)
        db.add(app)
        await db.flush()
    return app


async def create_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    app_id: uuid.UUID | None = None,
    title: str | None = None,
) -> ChatSession:
    session = ChatSession(
        app_id=app_id,
        created_by=user_id,
        title=title or "New conversation",
    )
    db.add(session)
    await db.flush()
    return session


async def get_session_history(db: AsyncSession, session_id: uuid.UUID) -> list[ChatTurn]:
    result = await db.execute(
        select(ChatTurn)
        .where(ChatTurn.session_id == session_id)
        .order_by(ChatTurn.turn_index)
    )
    return list(result.scalars().all())


async def stream_chat(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_message: str,
    api_key: str,
) -> AsyncIterator[str]:
    """Async generator yielding SSE events for a single chat turn.

    After streaming:
    - Extracts generated files and commits them to the app's git repo
    - Auto-generates session title on the first exchange
    """
    # ── Fetch session + history ───────────────────────────────────────────────
    session_result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    chat_session = session_result.scalar_one_or_none()

    history = await get_session_history(db, session_id)
    is_first_turn = len(history) == 0

    # ── Load existing files for app context ──────────────────────────────────
    app_slug: str | None = None
    existing_files = []
    if chat_session and chat_session.app_id:
        app_result = await db.execute(select(App).where(App.id == chat_session.app_id))
        app = app_result.scalar_one_or_none()
        if app:
            app_slug = app.slug
            existing_files = get_current_files(app_slug)

    system_prompt = _build_system_prompt(existing_files)

    # ── Persist user turn ─────────────────────────────────────────────────────
    user_turn = ChatTurn(
        session_id=session_id,
        turn_index=len(history),
        role="user",
        content=user_message,
    )
    db.add(user_turn)
    await db.commit()

    # ── Build Claude messages ─────────────────────────────────────────────────
    messages = [{"role": t.role, "content": t.content} for t in history]
    messages.append({"role": "user", "content": user_message})

    client = AsyncAnthropic(api_key=api_key)
    chunks: list[str] = []
    input_tokens = output_tokens = 0

    # ── Stream from Claude ────────────────────────────────────────────────────
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                chunks.append(text)
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"

            final = await stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        return

    full_response = "".join(chunks)

    # ── Persist assistant turn ────────────────────────────────────────────────
    assistant_turn = ChatTurn(
        session_id=session_id,
        turn_index=len(history) + 1,
        role="assistant",
        content=full_response,
        token_count=output_tokens,
    )
    db.add(assistant_turn)

    # ── Commit generated files to git ─────────────────────────────────────────
    commit_sha: str | None = None
    generated_files = extract_files(full_response)
    if generated_files and app_slug:
        try:
            commit_sha = commit_files(
                app_slug,
                generated_files,
                message=f"feat: {user_message[:72]}",
            )
            if commit_sha:
                assistant_turn.git_commit_sha = commit_sha
                app_id_str = str(chat_session.app_id) if chat_session and chat_session.app_id else None
                yield f"data: {json.dumps({'type': 'files_committed', 'app_id': app_id_str, 'app_slug': app_slug, 'commit_sha': commit_sha, 'file_count': len(generated_files)})}\n\n"
        except Exception as exc:
            log.warning("Git commit failed for app %s: %s", app_slug, exc)

        # ── Enqueue post-gen security scan (non-blocking) ─────────────────────
        try:
            from app.workers.scan_task import scan_generated_code
            scan_generated_code.apply_async(
                kwargs={
                    "turn_id": str(assistant_turn.id),
                    "files_json": {f.path: f.content for f in generated_files},
                    "org_slug": app_slug.split("-")[0] if "-" in app_slug else "unknown",
                },
                queue="scan",
            )
        except Exception as exc:
            log.warning("Failed to enqueue scan task: %s", exc)

    # ── Update session ────────────────────────────────────────────────────────
    if chat_session:
        chat_session.last_active_at = datetime.now(timezone.utc)

    await db.commit()

    # ── Auto-generate session title on first exchange (background) ────────────
    if is_first_turn and chat_session and chat_session.title in (None, "New conversation"):
        async def _update_title():
            try:
                title = await _generate_title(api_key, user_message, full_response[:300])
                chat_session.title = title
                await db.commit()
            except Exception:
                pass

        asyncio.create_task(_update_title())

    yield f"data: {json.dumps({'type': 'done', 'turn_id': str(assistant_turn.id), 'input_tokens': input_tokens, 'output_tokens': output_tokens, 'commit_sha': commit_sha, 'files_saved': len(generated_files)})}\n\n"

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic
from sqlalchemy import select

from app.api.deps import TenantContext
from app.models.org import App, ChatSession, ChatTurn
from app.services import chat_tools_service
from app.services.chat_tools_service import ChatToolError, SimulationGateRequired
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

## Infrastructure actions — tools only, never prose

You have exactly three tools for anything infra-related: `simulate_app`, `deploy_app`, \
and `get_app_status`. These are the ONLY ways to actually run, deploy, or check the status \
of the user's app — you have no other mechanism.

- Never write Terraform, CI/CD YAML, shell deploy scripts, or "run this yourself" instructions \
  as a way to satisfy a deploy/simulate/run request. A Dockerfile as part of the generated \
  application is fine; a Dockerfile or script presented AS the deployment mechanism is not.
- Never state that a deployment or simulation happened, is in progress, or is live unless you \
  called the corresponding tool and are reporting its actual result.
- If asked whether the app is live, deployed, or what its URL is, call `get_app_status` rather \
  than inferring from earlier conversation — status claims must come from that tool's result.
- Call `simulate_app`/`deploy_app` only on an explicit request to preview/simulate/test-run or \
  deploy/ship/publish/go-live — never speculatively, and never merely to explain what they do.
"""

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "simulate_app",
        "description": (
            "Start a temporary, non-billable preview of the current app in Loomaris's own "
            "sandbox — this is NOT a real deployment, it's an ephemeral live preview that "
            "expires on its own. Call this only when the user explicitly asks to preview, "
            "try, test-run, or simulate the app."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "deploy_app",
        "description": (
            "Deploy the current app to the user's own connected cloud account. This provisions "
            "real, billable infrastructure and is gated behind a passing simulation of the "
            "current code — the user will be shown a confirmation step (and may override the "
            "gate there) before anything actually happens. Call this only on an explicit request "
            "to deploy, ship, publish, or go live."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "environment": {
                    "type": "string",
                    "enum": ["staging", "production"],
                    "description": "Which environment to deploy to.",
                }
            },
            "required": ["environment"],
        },
    },
    {
        "name": "get_app_status",
        "description": (
            "Look up the app's real current deployment and simulation status (running/live "
            "URL, last deploy result, etc). Call this whenever asked whether the app is live, "
            "deployed, or running, or what its URL is."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

# Tools that cause a real, billable/side-effecting action and must be confirmed by the user
# before executing. get_app_status is read-only and is auto-executed inline instead.
_CONFIRM_REQUIRED_TOOLS = {"simulate_app", "deploy_app"}


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


def _tool_call_summary(tool_name: str, tool_input: dict) -> str:
    if tool_name == "simulate_app":
        return "Start a temporary preview of the current app"
    if tool_name == "deploy_app":
        env = tool_input.get("environment", "production")
        return f"Deploy the current app to {env} — real, billable infrastructure"
    return f"Run {tool_name}"


async def _stream_claude(client: AsyncAnthropic, system_prompt: str, messages: list) -> AsyncIterator[tuple[str, Any]]:
    """Stream a single Claude turn. Yields ('text', chunk) for each text delta, then
    exactly one ('final', message) with the fully-parsed final message (including any
    tool_use blocks — get_final_message() reconstructs the complete message regardless
    of what text_stream surfaced live, so this does not miss tool calls)."""
    async with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=system_prompt,
        messages=messages,
        tools=_TOOLS,
    ) as stream:
        async for text in stream.text_stream:
            yield ("text", text)
        final = await stream.get_final_message()
        yield ("final", final)


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


def _slugify(name: str) -> str:
    """Turn arbitrary text (including raw user chat messages, not just a
    dedicated "create app" form field) into a safe git_service.REPOS_ROOT
    path segment: lowercase, only [a-z0-9-], no leading/trailing/repeated
    hyphens, no "." or "/" that could escape the repos directory."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80] or "app"


async def get_or_create_app(db, *, name: str, app_type: str = "web") -> App:
    slug = _slugify(name)
    result = await db.execute(select(App).where(App.slug == slug))
    app = result.scalar_one_or_none()
    if not app:
        app = App(name=name, slug=slug, app_type=app_type)
        db.add(app)
        await db.flush()
    return app


async def create_session(
    db,
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


async def get_session_history(db, session_id: uuid.UUID) -> list[ChatTurn]:
    result = await db.execute(
        select(ChatTurn)
        .where(ChatTurn.session_id == session_id)
        .order_by(ChatTurn.turn_index)
    )
    return list(result.scalars().all())


async def _load_app_for_session(db, chat_session: ChatSession | None) -> App | None:
    if not chat_session or not chat_session.app_id:
        return None
    result = await db.execute(select(App).where(App.id == chat_session.app_id))
    return result.scalar_one_or_none()


def _enqueue_scan(app_slug: str, assistant_turn: ChatTurn, generated_files: list) -> None:
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


def _schedule_title_update(ctx: TenantContext, chat_session: ChatSession, api_key: str, user_message: str, assistant_snippet: str) -> None:
    async def _update_title():
        try:
            title = await _generate_title(api_key, user_message, assistant_snippet)
            chat_session.title = title
            await ctx.session.commit()
        except Exception:
            pass

    asyncio.create_task(_update_title())


async def stream_chat(
    ctx: TenantContext,
    session_id: uuid.UUID,
    user_message: str,
    api_key: str,
) -> AsyncIterator[str]:
    """Async generator yielding SSE events for a single chat turn.

    After streaming:
    - Extracts generated files and commits them to the app's git repo
    - Auto-generates session title on the first exchange
    - If Claude calls simulate_app/deploy_app, the turn ends awaiting confirmation
      (tool_call_pending) instead of executing anything — see
      resume_after_tool_confirmation() for what happens after the user confirms.
    - If Claude calls get_app_status, it's auto-executed (read-only) and the
      conversation continues in the same turn so Claude can answer using the real result.
    """
    db = ctx.session

    # ── Fetch session + history ───────────────────────────────────────────────
    session_result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    chat_session = session_result.scalar_one_or_none()

    history = await get_session_history(db, session_id)
    is_first_turn = len(history) == 0

    # ── Load app + its current files for context and tool execution ───────────
    app_obj = await _load_app_for_session(db, chat_session)
    app_slug = app_obj.slug if app_obj else None
    existing_files = get_current_files(app_slug) if app_slug else []

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
    messages: list[dict] = [{"role": t.role, "content": t.content} for t in history]
    messages.append({"role": "user", "content": user_message})

    client = AsyncAnthropic(api_key=api_key)
    chunks: list[str] = []
    input_tokens = output_tokens = 0
    tool_use_block = None
    auto_status_rounds = 0

    # ── Stream from Claude, auto-resolving read-only get_app_status calls ─────
    try:
        while True:
            final = None
            async for kind, payload in _stream_claude(client, system_prompt, messages):
                if kind == "text":
                    chunks.append(payload)
                    yield f"data: {json.dumps({'type': 'text', 'text': payload})}\n\n"
                else:
                    final = payload

            input_tokens += final.usage.input_tokens
            output_tokens += final.usage.output_tokens
            tool_use_block = next((b for b in final.content if b.type == "tool_use"), None)

            if tool_use_block and tool_use_block.name == "get_app_status" and auto_status_rounds == 0:
                auto_status_rounds += 1
                status = (
                    await chat_tools_service.get_app_status(ctx, app_obj)
                    if app_obj
                    else {"error": "No app has been created in this chat yet."}
                )
                messages.append({"role": "assistant", "content": final.content})
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": json.dumps(status, default=str),
                    }],
                })
                yield f"data: {json.dumps({'type': 'tool_result', 'tool_use_id': tool_use_block.id, 'tool_name': 'get_app_status', 'status': 'ok', 'detail': status})}\n\n"
                continue

            break
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

    pending_tool = (
        tool_use_block
        if tool_use_block and tool_use_block.name in _CONFIRM_REQUIRED_TOOLS
        else None
    )
    if pending_tool:
        assistant_turn.pending_tool_use_id = pending_tool.id
        assistant_turn.pending_tool_name = pending_tool.name
        assistant_turn.pending_tool_input = pending_tool.input
        assistant_turn.tool_status = "pending"

    db.add(assistant_turn)

    # ── Commit generated files to git ─────────────────────────────────────────
    commit_sha: str | None = None
    generated_files = extract_files(full_response)

    # A session started from a standalone "New conversation" (POST /chat/sessions,
    # no app_id) has no linked App until now — get_or_create_app() is otherwise only
    # ever called from the explicit POST /apps route. Without this, generated files
    # here are silently discarded: no git commit, no files_committed event, no
    # ActionBar, and simulate_app/deploy_app calls Claude makes have nothing to act
    # on. Lazily create + link one the first time a session actually produces files.
    if generated_files and not app_slug and chat_session:
        # The auto-generated session title (_schedule_title_update) hasn't run yet on
        # a first turn — title is still the "New conversation" placeholder — so derive
        # the name from the user's message instead. Suffix with part of the session id
        # so two unrelated sessions describing similarly-named apps ("calculator") don't
        # collide on get_or_create_app's slug lookup and silently share one app/repo.
        base_name = (
            chat_session.title
            if chat_session.title and chat_session.title != "New conversation"
            else user_message[:60]
        )
        app_obj = await get_or_create_app(db, name=f"{base_name} {str(session_id)[:8]}")
        chat_session.app_id = app_obj.id
        await db.commit()
        app_slug = app_obj.slug

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

        _enqueue_scan(app_slug, assistant_turn, generated_files)

    # ── Update session ────────────────────────────────────────────────────────
    if chat_session:
        chat_session.last_active_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(assistant_turn)

    # ── Auto-generate session title on first exchange (background) ────────────
    if is_first_turn and chat_session and chat_session.title in (None, "New conversation"):
        _schedule_title_update(ctx, chat_session, api_key, user_message, full_response[:300])

    # ── Tool call awaiting confirmation ────────────────────────────────────────
    if pending_tool:
        summary = _tool_call_summary(pending_tool.name, pending_tool.input)
        yield f"data: {json.dumps({'type': 'tool_call_pending', 'turn_id': str(assistant_turn.id), 'tool_use_id': pending_tool.id, 'tool_name': pending_tool.name, 'input': pending_tool.input, 'summary': summary})}\n\n"

    yield f"data: {json.dumps({'type': 'done', 'turn_id': str(assistant_turn.id), 'input_tokens': input_tokens, 'output_tokens': output_tokens, 'commit_sha': commit_sha, 'files_saved': len(generated_files)})}\n\n"


async def resume_after_tool_confirmation(
    ctx: TenantContext,
    session_id: uuid.UUID,
    turn_id: uuid.UUID,
    decision: str,
    api_key: str,
    *,
    cloud_account_id: uuid.UUID | None = None,
    deploy_without_preview: bool = False,
) -> AsyncIterator[str]:
    """Resume a chat turn that ended on a pending simulate_app/deploy_app tool_use,
    after the user approved or denied it. On approve, actually executes the tool via
    chat_tools_service (the same functions the HTTP routes use), builds a real
    tool_result from the outcome, then lets Claude produce a grounded follow-up."""
    db = ctx.session

    turn_result = await db.execute(
        select(ChatTurn).where(ChatTurn.id == turn_id, ChatTurn.session_id == session_id)
    )
    turn = turn_result.scalar_one_or_none()
    if not turn or turn.tool_status != "pending" or not turn.pending_tool_use_id:
        yield f"data: {json.dumps({'type': 'error', 'message': 'No pending tool call found for this turn.'})}\n\n"
        return

    session_result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    chat_session = session_result.scalar_one_or_none()
    app_obj = await _load_app_for_session(db, chat_session)

    tool_use_id = turn.pending_tool_use_id
    tool_name = turn.pending_tool_name
    tool_input: dict = turn.pending_tool_input or {}

    if decision == "approve":
        try:
            if not app_obj:
                raise ChatToolError("No app associated with this chat.")
            if tool_name == "simulate_app":
                sim = await chat_tools_service.execute_simulate(ctx, app_obj)
                result: dict = {"ok": True, "session_id": str(sim.id), "status": sim.status}
            elif tool_name == "deploy_app":
                if not cloud_account_id:
                    raise ChatToolError("No cloud account specified for this deploy.")
                deployment, task_id = await chat_tools_service.execute_deploy(
                    ctx,
                    app_obj,
                    environment=tool_input.get("environment", "production"),
                    cloud_account_id=cloud_account_id,
                    deploy_without_preview=deploy_without_preview,
                )
                result = {
                    "ok": True,
                    "deployment_id": str(deployment.id),
                    "task_id": task_id,
                    "status": deployment.status,
                }
            else:
                raise ChatToolError(f"Unknown tool '{tool_name}'.")
        except SimulationGateRequired as exc:
            result = {"ok": False, "error": "simulation_required", "message": exc.gate.message}
        except ChatToolError as exc:
            result = {"ok": False, "error": "tool_error", "message": str(exc)}
    else:
        result = {"ok": False, "error": "declined", "message": "The user declined this action."}

    turn.tool_status = "approved" if decision == "approve" else "denied"
    await db.commit()

    yield f"data: {json.dumps({'type': 'tool_result', 'tool_use_id': tool_use_id, 'tool_name': tool_name, 'status': 'ok' if result.get('ok') else 'error', 'detail': result})}\n\n"

    # ── Reconstruct the conversation so the assistant turn ending in tool_use is
    #    immediately followed by the tool_result, per the API's tool-use contract ──
    history = await get_session_history(db, session_id)
    messages: list[dict] = []
    for t in history:
        if t.id == turn.id:
            content_blocks: list[dict] = []
            if t.content:
                content_blocks.append({"type": "text", "text": t.content})
            content_blocks.append({"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": tool_input})
            messages.append({"role": t.role, "content": content_blocks})
        else:
            messages.append({"role": t.role, "content": t.content})
    messages.append({
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(result, default=str)}],
    })

    existing_files = get_current_files(app_obj.slug) if app_obj else []
    system_prompt = _build_system_prompt(existing_files)

    client = AsyncAnthropic(api_key=api_key)
    chunks: list[str] = []
    input_tokens = output_tokens = 0
    try:
        final = None
        async for kind, payload in _stream_claude(client, system_prompt, messages):
            if kind == "text":
                chunks.append(payload)
                yield f"data: {json.dumps({'type': 'text', 'text': payload})}\n\n"
            else:
                final = payload
        input_tokens = final.usage.input_tokens
        output_tokens = final.usage.output_tokens
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        return

    full_response = "".join(chunks)
    follow_up_turn = ChatTurn(
        session_id=session_id,
        turn_index=len(history) + 1,
        role="assistant",
        content=full_response,
        token_count=output_tokens,
    )
    db.add(follow_up_turn)
    if chat_session:
        chat_session.last_active_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(follow_up_turn)

    yield f"data: {json.dumps({'type': 'done', 'turn_id': str(follow_up_turn.id), 'input_tokens': input_tokens, 'output_tokens': output_tokens, 'commit_sha': None, 'files_saved': 0})}\n\n"

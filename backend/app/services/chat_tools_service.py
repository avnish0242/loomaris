"""Shared implementations for "simulate", "deploy", and "get status" — the three
side-effecting/read operations exposed both as HTTP routes (`apps.py`) and as
chat tools (`chat_service.py`'s tool-calling loop). Keeping a single implementation
here means the simulation gate, budget checks, and status-reporting logic can't
drift between the button-driven and chat-driven paths.
"""
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext
from app.models.org import App, Deployment, SimulationSession
from app.models.platform import CloudAccount
from app.services.git_service import get_current_files, get_head_sha
from app.services.simulation_gate_service import GateStatus, get_gate_status


class ChatToolError(Exception):
    """A tool call failed for an ordinary reason (no code yet, no cloud account, etc).
    Callers turn this into an HTTPException (routes) or a tool_result error (chat)."""


class SimulationGateRequired(Exception):
    """Deploy was blocked by the simulation gate and wasn't overridden."""

    def __init__(self, gate: GateStatus):
        self.gate = gate
        super().__init__(gate.message)


async def execute_simulate(ctx: TenantContext, app: App) -> SimulationSession:
    from app.workers.simulate_task import run_simulation

    files = get_current_files(app.slug)
    if not files:
        raise ChatToolError("No generated code yet — chat with Loomaris to build something first.")

    session = SimulationSession(
        app_id=app.id,
        user_id=ctx.user.id,
        status="building",
        commit_sha=get_head_sha(app.slug),
    )
    ctx.session.add(session)
    await ctx.session.commit()
    await ctx.session.refresh(session)

    run_simulation.apply_async(
        kwargs={
            "app_id": str(app.id),
            "org_slug": ctx.org.slug,
            "user_id": str(ctx.user.id),
            "session_id": str(session.id),
        },
        queue="deploy",
    )
    return session


async def resolve_cloud_account(
    org_id: uuid.UUID, platform_db: AsyncSession, *, explicit_account_id: uuid.UUID | None = None
) -> CloudAccount | None:
    """Pick which cloud account a deploy should use.

    An explicit id (from the DeployModal, or a chat confirmation picker) always wins.
    Otherwise, auto-select only if the org has exactly one verified account — Claude
    never supplies an account id itself (it has no way to know a real UUID), so this
    is the only place account selection happens for chat-triggered deploys.
    """
    if explicit_account_id:
        result = await platform_db.execute(
            select(CloudAccount).where(
                CloudAccount.id == explicit_account_id, CloudAccount.org_id == org_id
            )
        )
        return result.scalar_one_or_none()

    result = await platform_db.execute(
        select(CloudAccount).where(CloudAccount.org_id == org_id, CloudAccount.status == "verified")
    )
    accounts = result.scalars().all()
    return accounts[0] if len(accounts) == 1 else None


async def execute_deploy(
    ctx: TenantContext,
    app: App,
    *,
    environment: str,
    cloud_account_id: uuid.UUID,
    deploy_without_preview: bool,
) -> tuple[Deployment, str]:
    """Returns (deployment row, celery task id)."""
    from app.workers.deploy_task import cloud_deploy_task

    files = get_current_files(app.slug)
    if not files:
        raise ChatToolError("No generated code yet — chat with Loomaris to build something first.")

    gate = await get_gate_status(app, ctx.session)
    if not gate.passed and not deploy_without_preview:
        raise SimulationGateRequired(gate)

    deployment = Deployment(
        app_id=app.id,
        cloud_account_id=cloud_account_id,
        environment=environment,
        status="queued",
        commit_sha=gate.head_sha,
        bypassed_simulation_gate=not gate.passed,
    )
    ctx.session.add(deployment)
    await ctx.session.commit()
    await ctx.session.refresh(deployment)

    task = cloud_deploy_task.apply_async(
        kwargs={
            "app_id": str(app.id),
            "deployment_id": str(deployment.id),
            "cloud_account_id": str(cloud_account_id),
            "environment": environment,
            "confirm_cost": True,
            "env_vars": {},
            "org_slug": ctx.org.slug,
        },
        queue="deploy",
    )
    return deployment, task.id


async def get_app_status(ctx: TenantContext, app: App) -> dict:
    """Real, DB-backed status — this is what grounds chat's answers to
    "is it live?" / "did the deploy finish?" instead of the model guessing."""
    dep_result = await ctx.session.execute(
        select(Deployment).where(Deployment.app_id == app.id).order_by(desc(Deployment.created_at)).limit(1)
    )
    latest_deployment = dep_result.scalar_one_or_none()

    sim_result = await ctx.session.execute(
        select(SimulationSession)
        .where(SimulationSession.app_id == app.id)
        .order_by(desc(SimulationSession.created_at))
        .limit(1)
    )
    latest_simulation = sim_result.scalar_one_or_none()

    gate = await get_gate_status(app, ctx.session)

    return {
        "app_slug": app.slug,
        "deployment": (
            {
                "id": str(latest_deployment.id),
                "status": latest_deployment.status,
                "environment": latest_deployment.environment,
                "url": (latest_deployment.outputs or {}).get("alb_url")
                or (latest_deployment.outputs or {}).get("cdn_url")
                or (latest_deployment.outputs or {}).get("api_url"),
                "deployed_at": latest_deployment.deployed_at.isoformat()
                if latest_deployment.deployed_at
                else None,
            }
            if latest_deployment
            else None
        ),
        "simulation": (
            {
                "id": str(latest_simulation.id),
                "status": latest_simulation.status,
                "url": latest_simulation.url,
                "expires_at": latest_simulation.expires_at.isoformat()
                if latest_simulation.expires_at
                else None,
            }
            if latest_simulation
            else None
        ),
        "deploy_gate_passed": gate.passed,
    }

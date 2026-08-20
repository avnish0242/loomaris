"""The "must have a passing simulation before you can deploy" gate.

Strict semantics: only a simulation session that is CURRENTLY running (status
'running', not yet expired) for the app's EXACT current git HEAD satisfies the
gate. A simulation that succeeded earlier but has since expired/stopped, or one
run against an older commit, does not count — every deploy (including a redeploy
of an already-live app) must be preceded by an active preview of that exact code.

This module is the single source of truth for the check; both the HTTP
`/cloud-deploy` route and the chat `deploy_app` tool call the same function here
so the enforcement can't drift between the two entry points.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org import App, SimulationSession
from app.services.git_service import get_head_sha


@dataclass
class GateStatus:
    passed: bool
    head_sha: str | None
    simulation: SimulationSession | None
    message: str


async def get_gate_status(app: App, db: AsyncSession) -> GateStatus:
    head_sha = get_head_sha(app.slug)

    if not head_sha:
        return GateStatus(
            passed=False,
            head_sha=None,
            simulation=None,
            message="No generated code yet — chat with Loomaris first, then simulate before deploying.",
        )

    result = await db.execute(
        select(SimulationSession)
        .where(
            SimulationSession.app_id == app.id,
            SimulationSession.commit_sha == head_sha,
            SimulationSession.status == "running",
        )
        .order_by(SimulationSession.created_at.desc())
        .limit(1)
    )
    sim = result.scalar_one_or_none()

    if sim and sim.expires_at is not None and sim.expires_at <= datetime.now(timezone.utc):
        sim = None

    if sim:
        return GateStatus(
            passed=True,
            head_sha=head_sha,
            simulation=sim,
            message=f"Simulation of commit {head_sha[:8]} is running.",
        )

    return GateStatus(
        passed=False,
        head_sha=head_sha,
        simulation=None,
        message=(
            f"No running simulation of the current code (commit {head_sha[:8]}). "
            "Run a simulation first, or explicitly deploy without previewing."
        ),
    )

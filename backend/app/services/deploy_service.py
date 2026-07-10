"""
Phase 1 deploy: builds a Docker image from generated files and runs it locally.
Uses the host Docker daemon via the mounted socket (/var/run/docker.sock).
Phase 2 will replace this with Pulumi IaC targeting real cloud accounts.
"""
import asyncio
import hashlib
import io
import json
import logging
import tarfile
from dataclasses import dataclass
from typing import AsyncIterator

import docker
from docker.errors import BuildError, DockerException

from app.services.git_service import GeneratedFile

log = logging.getLogger(__name__)

# Ports 8100-8999 are reserved for local preview deployments
_PORT_BASE = 8100
_PORT_RANGE = 900


def _pick_port(app_slug: str) -> int:
    """Deterministic port from slug. Uses MD5 so the result is stable across process restarts."""
    return _PORT_BASE + (int(hashlib.md5(app_slug.encode()).hexdigest(), 16) % _PORT_RANGE)


def _make_tar(files: list[GeneratedFile]) -> io.BytesIO:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in files:
            encoded = f.content.encode("utf-8")
            info = tarfile.TarInfo(name=f.path)
            info.size = len(encoded)
            tar.addfile(info, io.BytesIO(encoded))
    buf.seek(0)
    return buf


@dataclass
class DeployResult:
    container_id: str
    url: str
    port: int
    image_tag: str
    status: str


async def build_and_deploy(
    app_slug: str,
    files: list[GeneratedFile],
) -> AsyncIterator[str]:
    """
    Async generator yielding SSE-formatted deploy log events.
    Builds a Docker image, stops any previous container, starts the new one.
    """

    def _sse(type_: str, **kwargs) -> str:
        return f"data: {json.dumps({'type': type_, **kwargs})}\n\n"

    has_dockerfile = any(f.path.lower() in ("dockerfile", "docker/dockerfile") for f in files)
    if not has_dockerfile:
        yield _sse("error", message="No Dockerfile found in generated files. Ask Loomaris to add one.")
        return

    image_tag = f"loomaris-{app_slug}:latest"
    port = _pick_port(app_slug)

    yield _sse("log", text=f"▶ Building image {image_tag}…\n")

    try:
        client = docker.from_env(timeout=120)
    except DockerException as e:
        yield _sse("error", message=f"Cannot connect to Docker: {e}")
        return

    # --- Build phase (runs in thread so it doesn't block the event loop) ---
    build_logs: list[str] = []
    build_error: list[str] = []

    def _do_build():
        tar_buf = _make_tar(files)
        for chunk in client.api.build(
            fileobj=tar_buf,
            custom_context=True,
            tag=image_tag,
            rm=True,
            decode=True,
        ):
            if "stream" in chunk:
                build_logs.append(chunk["stream"])
            elif "error" in chunk:
                build_error.append(chunk["error"])

    loop = asyncio.get_event_loop()
    build_task = loop.run_in_executor(None, _do_build)

    # Stream buffered logs while build runs
    prev_len = 0
    while not build_task.done():
        await asyncio.sleep(0.3)
        new = build_logs[prev_len:]
        for line in new:
            if line.strip():
                yield _sse("log", text=line)
        prev_len = len(build_logs)

    try:
        await build_task
    except Exception as exc:
        yield _sse("error", message=f"Build exception: {exc}")
        return

    # Flush remaining logs
    for line in build_logs[prev_len:]:
        if line.strip():
            yield _sse("log", text=line)

    if build_error:
        yield _sse("error", message=f"Build failed: {build_error[-1]}")
        return

    yield _sse("log", text=f"✓ Image built\n")

    # --- Stop any existing container for this app ---
    container_name = f"loomaris-preview-{app_slug}"
    try:
        old = client.containers.get(container_name)
        yield _sse("log", text=f"⏹ Stopping previous container…\n")
        old.stop(timeout=5)
        old.remove()
    except docker.errors.NotFound:
        pass

    # --- Run new container ---
    yield _sse("log", text=f"▶ Starting container on port {port}…\n")
    try:
        container = client.containers.run(
            image_tag,
            detach=True,
            name=container_name,
            ports={"8000/tcp": port},
            labels={"loomaris.app": app_slug, "loomaris.managed": "true"},
            restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
        )
    except Exception as exc:
        yield _sse("error", message=f"Failed to start container: {exc}")
        return

    # Poll until running or give up after 10 s
    for _ in range(20):
        await asyncio.sleep(0.5)
        container.reload()
        if container.status == "running":
            break
        if container.status not in ("created", "restarting"):
            logs = container.logs(tail=20).decode("utf-8", errors="replace")
            yield _sse("error", message=f"Container exited immediately. Logs:\n{logs}")
            return

    url = f"http://localhost:{port}"
    yield _sse("log", text=f"✓ Running at {url}\n")
    yield _sse("done", url=url, container_id=container.id[:12], port=port, image_tag=image_tag)


async def get_container_status(app_slug: str) -> dict:
    """Return current status of the app's preview container."""
    container_name = f"loomaris-preview-{app_slug}"
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.reload()
        port = _pick_port(app_slug)
        return {
            "running": container.status == "running",
            "status": container.status,
            "url": f"http://localhost:{port}",
            "container_id": container.id[:12],
        }
    except docker.errors.NotFound:
        return {"running": False, "status": "not_deployed", "url": None, "container_id": None}
    except DockerException:
        return {"running": False, "status": "docker_unavailable", "url": None, "container_id": None}

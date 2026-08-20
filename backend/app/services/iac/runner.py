"""
Pulumi runner — executes generated Pulumi programs in an isolated Docker container.
Phase 2: Docker container with resource limits (no --privileged).
Phase 3: Firecracker microVM for hardware-level isolation.
"""
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_RUNNER_IMAGE = "loomaris/pulumi-runner:latest"
_PULUMI_STATE_BUCKET = os.environ.get("PULUMI_STATE_BUCKET", "")


@dataclass
class PreviewResult:
    success: bool
    resource_count: int = 0
    plan_summary: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class ApplyResult:
    success: bool
    outputs: dict = field(default_factory=dict)
    resource_count: int = 0
    error: str | None = None


@dataclass
class DestroyResult:
    success: bool
    error: str | None = None


def _pulumi_backend_url(stack_name: str) -> str:
    """Return the Pulumi state backend URL for this stack.

    When PULUMI_STATE_BUCKET is configured, use S3 so state persists across
    container invocations (required for pulumi destroy to work). Falls back to
    ephemeral in-container tmpfs for local dev without an S3 bucket.
    """
    bucket = _PULUMI_STATE_BUCKET or os.environ.get("PULUMI_STATE_BUCKET", "")
    if bucket:
        return f"s3://{bucket}/{stack_name}"
    return "file:///pulumi-state"


def provider_env(provider: str, creds: dict) -> list[str]:
    """Map a provider-shaped credentials dict to the env vars its Pulumi plugin
    expects, as ["-e", "KEY=VALUE", ...] docker run args."""
    if provider == "aws":
        return [
            "-e", f"AWS_ACCESS_KEY_ID={creds.get('access_key_id', '')}",
            "-e", f"AWS_SECRET_ACCESS_KEY={creds.get('secret_access_key', '')}",
            "-e", f"AWS_SESSION_TOKEN={creds.get('session_token', '')}",
            "-e", f"AWS_DEFAULT_REGION={creds.get('region', 'us-east-1')}",
        ]
    if provider == "azure":
        return [
            "-e", f"ARM_CLIENT_ID={creds.get('client_id', '')}",
            "-e", f"ARM_CLIENT_SECRET={creds.get('client_secret', '')}",
            "-e", f"ARM_TENANT_ID={creds.get('tenant_id', '')}",
            "-e", f"ARM_SUBSCRIPTION_ID={creds.get('subscription_id', '')}",
        ]
    if provider == "gcp":
        return [
            "-e", f"GOOGLE_CREDENTIALS={creds.get('service_account_json', '')}",
            "-e", f"GOOGLE_PROJECT={creds.get('project_id', '')}",
        ]
    raise ValueError(f"Unsupported cloud provider: {provider!r}")


def _run_pulumi_in_container(
    program: str,
    stack_name: str,
    provider_creds: dict,
    command: list[str],
    timeout: int = 300,
    provider: str = "aws",
) -> tuple[bool, str, str]:
    """Run a pulumi command inside a resource-limited Docker container.

    Returns (success, stdout, stderr).
    """
    backend_url = _pulumi_backend_url(stack_name)
    # Per-stack passphrase keeps stacks isolated; derive from stack name so it's
    # stable across up/destroy without storing it separately.
    import hashlib
    passphrase = hashlib.sha256(f"loomaris-{stack_name}".encode()).hexdigest()[:32]

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write the Pulumi program
        program_path = os.path.join(tmpdir, "__main__.py")
        with open(program_path, "w") as f:
            f.write(program)

        # Write Pulumi.yaml project file
        project_path = os.path.join(tmpdir, "Pulumi.yaml")
        with open(project_path, "w") as f:
            f.write(f"name: {stack_name}\nruntime: python\n")

        tmpfs_args = ["--tmpfs=/tmp:rw,exec,size=128m"]
        if not backend_url.startswith("s3://"):
            # Only mount tmpfs state dir when using the local file backend
            tmpfs_args.append("--tmpfs=/pulumi-state:rw,size=64m")

        # Build docker run command with security constraints
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--network=host",           # needed to reach the cloud provider's API endpoints
            "--cpus=0.5",
            "--memory=512m",
            "--read-only",
            *tmpfs_args,
            # Mount the program directory (read-only)
            "-v", f"{tmpdir}:/app:ro",
            # Credentials as env vars (not files) — ephemeral for this container only
            *provider_env(provider, provider_creds),
            "-e", f"PULUMI_BACKEND_URL={backend_url}",
            "-e", f"PULUMI_CONFIG_PASSPHRASE={passphrase}",
            "-w", "/app",
            _RUNNER_IMAGE,
        ] + command

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", f"Pulumi command timed out after {timeout}s"
        except FileNotFoundError:
            return False, "", "Docker not available — cannot run Pulumi"
        except Exception as exc:
            return False, "", str(exc)


def pulumi_preview(program: str, provider_creds: dict, stack_name: str, provider: str = "aws") -> PreviewResult:
    """Run `pulumi preview` and return a summary of planned changes."""
    success, stdout, stderr = _run_pulumi_in_container(
        program=program,
        stack_name=stack_name,
        provider_creds=provider_creds,
        command=["pulumi", "preview", "--stack", stack_name, "--json", "--non-interactive"],
        timeout=120,
        provider=provider,
    )

    if not success:
        return PreviewResult(success=False, error=stderr or "pulumi preview failed")

    try:
        plan = json.loads(stdout) if stdout.strip() else {}
        steps = plan.get("steps", [])
        resource_count = len([s for s in steps if s.get("op") in ("create", "update", "replace")])
        return PreviewResult(success=True, resource_count=resource_count, plan_summary=plan)
    except json.JSONDecodeError:
        return PreviewResult(success=True, resource_count=0, plan_summary={"raw": stdout[:500]})


def pulumi_up(program: str, provider_creds: dict, stack_name: str, provider: str = "aws") -> ApplyResult:
    """Run `pulumi up` and return the stack outputs."""
    success, stdout, stderr = _run_pulumi_in_container(
        program=program,
        stack_name=stack_name,
        provider_creds=provider_creds,
        command=[
            "pulumi", "up",
            "--stack", stack_name,
            "--yes",
            "--non-interactive",
            "--json",
        ],
        timeout=600,
        provider=provider,
    )

    if not success:
        return ApplyResult(success=False, error=stderr or "pulumi up failed")

    # Extract outputs from stdout JSON
    outputs: dict = {}
    try:
        lines = [ln for ln in stdout.splitlines() if ln.strip().startswith("{")]
        for line in lines:
            data = json.loads(line)
            if "outputs" in data:
                outputs = {k: v.get("value") for k, v in data["outputs"].items()}
                break
    except Exception:
        pass

    return ApplyResult(success=True, outputs=outputs)


def pulumi_destroy(stack_name: str, provider_creds: dict, program: str = "", provider: str = "aws") -> DestroyResult:
    """Run `pulumi destroy` to tear down the stack."""
    success, stdout, stderr = _run_pulumi_in_container(
        program=program or "import pulumi",
        stack_name=stack_name,
        provider_creds=provider_creds,
        command=["pulumi", "destroy", "--stack", stack_name, "--yes", "--non-interactive"],
        timeout=600,
        provider=provider,
    )
    if not success:
        return DestroyResult(success=False, error=stderr or "pulumi destroy failed")
    return DestroyResult(success=True)

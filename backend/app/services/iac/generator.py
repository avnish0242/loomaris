"""
Generates a complete, runnable Pulumi Python program for the given app files.
Calls the appropriate AWS template based on the detected deploy target type.
"""
from app.services.git_service import GeneratedFile
from app.services.iac.detector import AppDeployTarget
from app.services.iac.aws_templates import (
    container_program,
    lambda_program,
    static_site_program,
)


def generate_pulumi_program(
    *,
    app_slug: str,
    files: list[GeneratedFile],
    aws_region: str,
    aws_account_id: str,
    target: AppDeployTarget,
) -> str:
    """Return a complete Pulumi Python program string for the given target type."""
    if target.type == "static":
        static_pairs = [(f.path, f.content) for f in files if not f.path.endswith((".py", ".ts", ".js"))]
        return static_site_program(app_slug, aws_region, static_pairs)

    if target.type == "lambda":
        return lambda_program(app_slug, aws_region)

    # Default: container (ECS Fargate)
    return container_program(app_slug, aws_region, aws_account_id)

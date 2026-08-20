"""
Generates a complete, runnable Pulumi Python program for the given app files.
Dispatches to the template module for the target cloud provider based on the
detected deploy target type (static / container / lambda) — detector.py's
classification is itself provider-agnostic and needs no changes per provider.
"""
from app.services.git_service import GeneratedFile
from app.services.iac import aws_templates, azure_templates, gcp_templates
from app.services.iac.detector import AppDeployTarget

_TEMPLATES = {
    "aws": aws_templates,
    "azure": azure_templates,
    "gcp": gcp_templates,
}


def generate_pulumi_program(
    *,
    app_slug: str,
    files: list[GeneratedFile],
    aws_region: str,
    aws_account_id: str,
    target: AppDeployTarget,
    provider: str = "aws",
) -> str:
    """Return a complete Pulumi Python program string for the given target type
    and cloud provider. `aws_region`/`aws_account_id` are kept as the parameter
    names for backward compatibility (most call sites still deploy to AWS) but
    are interpreted as "region"/"account or project id" for whichever provider
    is selected.
    """
    templates = _TEMPLATES.get(provider)
    if templates is None:
        raise ValueError(f"Unsupported cloud provider: {provider!r}")

    if target.type == "static":
        static_pairs = [(f.path, f.content) for f in files if not f.path.endswith((".py", ".ts", ".js"))]
        return templates.static_site_program(app_slug, aws_region, static_pairs)

    if target.type == "lambda":
        return templates.lambda_program(app_slug, aws_region)

    # Default: container
    if provider == "aws":
        return templates.container_program(app_slug, aws_region, aws_account_id)
    if provider == "gcp":
        return templates.container_program(app_slug, aws_region, aws_account_id)
    # Azure's container template has no account/project-id concept
    return templates.container_program(app_slug, aws_region)

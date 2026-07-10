"""
Validates a generated Pulumi Python program before execution.
Checks: Python syntax, resource allowlist per plan, Semgrep IaC rules.
"""
import ast
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_ALLOWED_RESOURCES_BY_PLAN: dict[str, list[str]] = {
    "trial":   ["aws.s3", "aws.cloudfront", "aws.lambda_", "aws.apigatewayv2"],
    "starter": ["aws.s3", "aws.cloudfront", "aws.lambda_", "aws.apigatewayv2", "aws.ecs", "aws.ecr", "aws.rds"],
    "pro":     ["*"],
}


@dataclass
class ValidationResult:
    valid: bool
    error: str | None = None
    security_issues: list[dict] = field(default_factory=list)


def _extract_resource_types(program: str) -> list[str]:
    """Extract aws.* resource types used in the Pulumi program."""
    try:
        tree = ast.parse(program)
        resources: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute):
                    # Pattern: aws.s3.Bucket(...) → "aws.s3"
                    if isinstance(func.value.value, ast.Name) and func.value.value.id == "aws":
                        resources.append(f"aws.{func.value.attr}")
        return list(set(resources))
    except Exception:
        return []


def _run_semgrep_iac(program: str) -> list[dict]:
    """Run custom IaC Semgrep rules against the Pulumi program."""
    rules_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "semgrep-rules", "loomaris-iac.yaml"
    )
    if not os.path.exists(rules_path):
        return []

    issues: list[dict] = []
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(program)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["semgrep", "--json", "--quiet", "--config", rules_path, tmp_path],
            capture_output=True, text=True, timeout=30,
        )
        import json
        if result.stdout:
            data = json.loads(result.stdout)
            for finding in data.get("results", []):
                issues.append({
                    "rule_id": finding.get("check_id"),
                    "message": finding.get("extra", {}).get("message", ""),
                    "severity": finding.get("extra", {}).get("severity", "WARNING"),
                    "line": finding.get("start", {}).get("line", 0),
                })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as exc:
        log.warning("IaC semgrep validation failed: %s", exc)
    finally:
        os.unlink(tmp_path)

    return issues


def validate(program: str, org_plan: str = "pro") -> ValidationResult:
    """Validate a Pulumi program before execution."""
    # 1. Python syntax check
    try:
        ast.parse(program)
    except SyntaxError as exc:
        return ValidationResult(valid=False, error=f"Syntax error in generated IaC: {exc}")

    # 2. Resource allowlist
    allowed = _ALLOWED_RESOURCES_BY_PLAN.get(org_plan, ["*"])
    if "*" not in allowed:
        used = _extract_resource_types(program)
        blocked = [r for r in used if not any(r.startswith(a) for a in allowed)]
        if blocked:
            return ValidationResult(
                valid=False,
                error=f"Resources not permitted on '{org_plan}' plan: {blocked}. Upgrade to access.",
            )

    # 3. Semgrep IaC security rules
    security_issues = _run_semgrep_iac(program)
    critical = [i for i in security_issues if i.get("severity", "").upper() == "ERROR"]
    if critical:
        msgs = "; ".join(i["message"] for i in critical[:3])
        return ValidationResult(
            valid=False,
            error=f"Security issues in generated IaC: {msgs}",
            security_issues=security_issues,
        )

    return ValidationResult(valid=True, security_issues=security_issues)

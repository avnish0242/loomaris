"""
Detects the deployment target type from generated app files.
Returns one of: "static" | "container" | "lambda"
"""
from dataclasses import dataclass

from app.services.git_service import GeneratedFile

_LAMBDA_ENTRYPOINTS = {"handler.py", "lambda_function.py", "handler.js", "index.js", "index.ts"}
_SERVER_EXTENSIONS = {".py", ".js", ".ts", ".go", ".rb", ".java"}
_SERVER_FRAMEWORKS = {
    "fastapi", "flask", "django", "express", "koa", "hono",
    "gin", "echo", "rails", "spring",
}


@dataclass
class AppDeployTarget:
    type: str           # "static" | "container" | "lambda"
    detected_runtime: str
    confidence: float


def detect_app_type(files: list[GeneratedFile]) -> AppDeployTarget:
    """Analyse generated files and return the best deployment target."""
    paths = {f.path.lower() for f in files}
    path_names = {f.path.split("/")[-1].lower() for f in files}
    all_content = "\n".join(f.content.lower() for f in files)

    # Container: has a Dockerfile
    has_dockerfile = any(
        p in ("dockerfile", "docker/dockerfile") or p.endswith("/dockerfile")
        for p in paths
    )
    if has_dockerfile:
        runtime = _detect_runtime(path_names, all_content)
        return AppDeployTarget(type="container", detected_runtime=runtime, confidence=0.95)

    # Lambda: has a known lambda entrypoint with a handler function
    has_lambda_entry = bool(path_names & _LAMBDA_ENTRYPOINTS)
    has_handler_fn = "def handler(" in all_content or "exports.handler" in all_content
    if has_lambda_entry and has_handler_fn:
        runtime = _detect_runtime(path_names, all_content)
        return AppDeployTarget(type="lambda", detected_runtime=runtime, confidence=0.9)

    # Static: has index.html and no server code
    has_index_html = "index.html" in path_names
    has_server_code = any(
        p.endswith(ext) for p in paths for ext in _SERVER_EXTENSIONS
    ) and any(fw in all_content for fw in _SERVER_FRAMEWORKS)
    if has_index_html and not has_server_code:
        return AppDeployTarget(type="static", detected_runtime="html", confidence=0.9)

    # Fallback: if there's server code without Dockerfile, treat as container
    # (Claude generates complete apps; assume Dockerfile was requested in next turn)
    runtime = _detect_runtime(path_names, all_content)
    return AppDeployTarget(type="container", detected_runtime=runtime, confidence=0.6)


def _detect_runtime(path_names: set[str], content: str) -> str:
    if "requirements.txt" in path_names or ".py" in str(path_names):
        return "python"
    if "package.json" in path_names:
        if "typescript" in content or ".ts" in str(path_names):
            return "nodejs-ts"
        return "nodejs"
    if "go.mod" in path_names:
        return "go"
    if "pom.xml" in path_names or "build.gradle" in path_names:
        return "java"
    return "unknown"

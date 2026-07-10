"""
Git-backed code persistence for generated apps.
Each app gets its own repo at /repos/{app_slug}/.
Every completed generation is a commit — full history, rollback-ready.
"""
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import git

REPOS_ROOT = Path("/repos")

# Configure git identity once per process
_GIT_CONFIGURED = False


def _ensure_git_config(repo: git.Repo) -> None:
    global _GIT_CONFIGURED
    if not _GIT_CONFIGURED:
        with repo.config_writer() as cfg:
            cfg.set_value("user", "name", "Loomaris")
            cfg.set_value("user", "email", "bot@loomaris.dev")
        _GIT_CONFIGURED = True


@dataclass
class GeneratedFile:
    path: str
    content: str


def extract_files(content: str) -> list[GeneratedFile]:
    """Parse ```file:path``` blocks from a Claude response."""
    pattern = re.compile(r"```file:([^\n]+)\n([\s\S]*?)```", re.MULTILINE)
    return [
        GeneratedFile(path=m.group(1).strip(), content=m.group(2))
        for m in pattern.finditer(content)
    ]


def _get_or_init_repo(app_slug: str) -> git.Repo:
    repo_path = REPOS_ROOT / app_slug
    repo_path.mkdir(parents=True, exist_ok=True)

    if (repo_path / ".git").exists():
        repo = git.Repo(repo_path)
    else:
        repo = git.Repo.init(repo_path)

    _ensure_git_config(repo)
    return repo


def commit_files(app_slug: str, files: list[GeneratedFile], message: str) -> str | None:
    """Write files and create a git commit. Returns the commit SHA or None if nothing to commit."""
    if not files:
        return None

    repo = _get_or_init_repo(app_slug)
    repo_path = Path(repo.working_dir)

    for f in files:
        target = repo_path / f.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.content, encoding="utf-8")
        repo.index.add([str(target.relative_to(repo_path))])

    # On the very first commit there is no HEAD, so index.diff("HEAD") raises BadName.
    # In that case we always have something to commit.
    try:
        has_changes = bool(repo.index.diff("HEAD")) or bool(repo.untracked_files)
    except git.exc.BadName:
        has_changes = True  # first commit in a brand-new repo

    if not has_changes:
        return None

    commit = repo.index.commit(message)
    return commit.hexsha


def get_current_files(app_slug: str) -> list[GeneratedFile]:
    """Return all files in the app's latest git commit."""
    repo_path = REPOS_ROOT / app_slug
    if not (repo_path / ".git").exists():
        return []

    try:
        repo = git.Repo(repo_path)
        if not repo.head.is_valid():
            return []
        files = []
        for item in repo.head.commit.tree.traverse():
            if item.type == "blob":
                try:
                    files.append(GeneratedFile(
                        path=item.path,
                        content=item.data_stream.read().decode("utf-8"),
                    ))
                except UnicodeDecodeError:
                    pass  # skip binary files
        return files
    except Exception:
        return []


def get_commit_log(app_slug: str, limit: int = 10) -> list[dict]:
    """Return recent commits as dicts with sha, message, date."""
    repo_path = REPOS_ROOT / app_slug
    if not (repo_path / ".git").exists():
        return []
    try:
        repo = git.Repo(repo_path)
        if not repo.head.is_valid():
            return []
        return [
            {
                "sha": c.hexsha[:8],
                "message": c.message.strip(),
                "date": c.committed_datetime.isoformat(),
            }
            for c in repo.iter_commits(max_count=limit)
        ]
    except Exception:
        return []


def checkout_commit(app_slug: str, sha: str) -> None:
    """Reset the working tree to a specific commit (detached HEAD)."""
    repo_path = REPOS_ROOT / app_slug
    if not (repo_path / ".git").exists():
        raise ValueError(f"No git repo found for app '{app_slug}'")
    repo = git.Repo(repo_path)
    repo.git.checkout(sha)


def create_zip_archive(app_slug: str) -> bytes:
    """Zip the current repo state for download."""
    files = get_current_files(app_slug)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.writestr(f"{app_slug}/{f.path}", f.content)
    return buf.getvalue()

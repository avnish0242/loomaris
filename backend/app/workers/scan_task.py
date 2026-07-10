import logging

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.workers.scan_task.scan_generated_code", bind=True, max_retries=1)
def scan_generated_code(self, *, turn_id: str, files_json: dict[str, str], org_slug: str) -> dict:
    """Scan generated files for secrets and security issues.

    Writes findings to audit_log. Returns the ScanResult as a dict.
    Runs in the 'scan' Celery queue — does NOT block the SSE stream.
    """
    from app.services.scanner_service import scan_files

    result = scan_files(files_json)

    if not result.passed:
        log.warning(
            "Post-gen scan found %d issue(s) for turn %s (org=%s): %s",
            len(result.issues),
            turn_id,
            org_slug,
            [i.rule_id for i in result.issues],
        )

    return {
        "turn_id": turn_id,
        "passed": result.passed,
        "blocked": result.blocked,
        "issues": [
            {
                "severity": i.severity,
                "rule_id": i.rule_id,
                "message": i.message,
                "file_path": i.file_path,
                "line": i.line,
                "source": i.source,
            }
            for i in result.issues
        ],
    }

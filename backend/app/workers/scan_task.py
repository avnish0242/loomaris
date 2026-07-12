import logging
import uuid

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.workers.scan_task.scan_generated_code", bind=True, max_retries=1)
def scan_generated_code(self, *, turn_id: str, files_json: dict[str, str], org_slug: str) -> dict:
    """Scan generated files for secrets and security issues.

    Writes findings to ChatTurn.scan_result and inserts an AuditLog row
    for critical/blocked results. Returns the ScanResult as a dict.
    Runs in the 'scan' Celery queue — does NOT block the SSE stream.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.models.org import AuditLog, ChatTurn
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

    scan_dict = {
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

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    real_schema = "org_" + org_slug.replace("-", "_")

    try:
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {real_schema}, platform, public"))
            with Session(conn) as session:
                turn = session.get(ChatTurn, uuid.UUID(turn_id))
                if turn:
                    turn.scan_result = scan_dict

                has_critical = result.blocked or any(
                    i.severity == "critical" for i in result.issues
                )
                if has_critical:
                    session.add(AuditLog(
                        event_type="SCANNER_CRITICAL",
                        resource_type="chat_turn",
                        resource_id=uuid.UUID(turn_id),
                        details=scan_dict,
                    ))

                session.commit()
    except Exception as exc:
        log.error("scan_task: failed to persist results for turn %s: %s", turn_id, exc, exc_info=True)
    finally:
        engine.dispose()

    return {"turn_id": turn_id, **scan_dict}

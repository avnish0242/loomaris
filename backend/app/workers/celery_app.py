from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "loomaris",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.deploy_task",
        "app.workers.destroy_task",
        "app.workers.simulate_task",
        "app.workers.cost_task",
        "app.workers.scan_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.deploy_task.*": {"queue": "deploy"},
        "app.workers.destroy_task.*": {"queue": "deploy"},
        "app.workers.simulate_task.*": {"queue": "deploy"},
        "app.workers.cost_task.*": {"queue": "cost"},
        "app.workers.scan_task.*": {"queue": "scan"},
    },
    task_default_queue="deploy",
)

from celery import Celery
from celery.schedules import crontab
from loguru import logger

from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "marches_publics",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.scraper_tasks"]
)

# Celery configuration
celery_app.conf.update(
    # Time zone
    timezone="Africa/Casablanca",
    enable_utc=True,
    
    # Task settings
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,  # 1 hour
    
    # Worker settings
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    
    # Beat schedule for periodic tasks
    beat_schedule={
        # Daily scraping at 2 AM
        "daily-scraping": {
            "task": "app.tasks.scraper_tasks.scheduled_scraping_task",
            "schedule": crontab(hour=2, minute=0),
            "args": (50,),  # Max 50 pages per day
        },
        
        # Clean up old logs every week
        "weekly-cleanup": {
            "task": "app.tasks.scraper_tasks.cleanup_old_data",
            "schedule": crontab(hour=1, minute=0, day_of_week=0),  # Sunday at 1 AM
        },
        
        # Generate daily statistics
        "daily-stats": {
            "task": "app.tasks.scraper_tasks.generate_daily_stats",
            "schedule": crontab(hour=23, minute=30),  # Daily at 11:30 PM
        },
    },
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)


# Task routes
celery_app.conf.task_routes = {
    "app.tasks.scraper_tasks.scraping_task": {"queue": "scraping"},
    "app.tasks.scraper_tasks.scheduled_scraping_task": {"queue": "scraping"},
    "app.tasks.scraper_tasks.cleanup_old_data": {"queue": "maintenance"},
    "app.tasks.scraper_tasks.generate_daily_stats": {"queue": "analytics"},
}


if __name__ == "__main__":
    celery_app.start()

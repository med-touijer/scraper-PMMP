from celery import current_task
from datetime import datetime, timedelta
from loguru import logger
from typing import Optional
import asyncio

from app.celery_app import celery_app
from app.services.scraper import scraper_service
from app.services.announcement import AnnouncementService
from app.models.announcement import ScraperConfig
from app.db.database import connect_to_mongo, close_mongo_connection


@celery_app.task(bind=True, name="app.tasks.scraper_tasks.scraping_task")
def scraping_task(self, max_pages: Optional[int] = None, start_page: int = 1):
    """Background scraping task"""
    try:
        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={"status": "Starting scraper", "progress": 0}
        )
        
        # Run async scraping
        result = asyncio.run(_async_scraping_wrapper(max_pages, start_page, self))
        
        return {
            "status": "completed",
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Scraping task failed: {e}")
        self.update_state(
            state="FAILURE",
            meta={"error": str(e), "timestamp": datetime.utcnow().isoformat()}
        )
        raise


async def _async_scraping_wrapper(max_pages: Optional[int], start_page: int, task):
    """Async wrapper for scraping with progress updates"""
    try:
        # Connect to database
        await connect_to_mongo()
        
        # Create config
        config = ScraperConfig(
            maxPages=max_pages,
            startPage=start_page,
            enabled=True
        )
        
        # Progress callback
        async def progress_callback(page: int, total_pages: Optional[int] = None):
            if total_pages:
                progress = int((page / total_pages) * 100)
            else:
                progress = page * 2  # Rough estimate
            
            task.update_state(
                state="PROGRESS",
                meta={
                    "status": f"Scraping page {page}",
                    "progress": min(progress, 95),
                    "current_page": page,
                    "total_pages": total_pages
                }
            )
        
        # Run scraping
        result = await scraper_service.scrape_pages(
            max_pages=max_pages,
            start_page=start_page,
            config=config
        )
        
        return result.dict()
        
    finally:
        await close_mongo_connection()


@celery_app.task(name="app.tasks.scraper_tasks.scheduled_scraping_task")
def scheduled_scraping_task(max_pages: int = 50):
    """Scheduled daily scraping task"""
    try:
        logger.info(f"Starting scheduled scraping task with max_pages={max_pages}")
        
        # Run scraping
        result = scraping_task.delay(max_pages=max_pages, start_page=1)
        
        return {
            "status": "scheduled",
            "task_id": result.id,
            "max_pages": max_pages,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Scheduled scraping task failed: {e}")
        raise


@celery_app.task(name="app.tasks.scraper_tasks.cleanup_old_data")
def cleanup_old_data():
    """Clean up old data and logs"""
    try:
        logger.info("Starting cleanup task")
        
        # This would contain cleanup logic
        asyncio.run(_async_cleanup())
        
        return {
            "status": "completed",
            "message": "Cleanup completed successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        raise


async def _async_cleanup():
    """Async cleanup operations"""
    try:
        await connect_to_mongo()
        
        # Clean up old announcements (older than 2 years)
        cutoff_date = datetime.utcnow() - timedelta(days=730)
        
        from app.db.database import get_announcements_collection
        collection = await get_announcements_collection()
        
        # Remove very old announcements that are no longer relevant
        result = await collection.delete_many({
            "datePublication": {"$lt": cutoff_date},
            "dateLimite": {"$lt": datetime.utcnow() - timedelta(days=365)}
        })
        
        logger.info(f"Cleaned up {result.deleted_count} old announcements")
        
        # Additional cleanup operations can be added here
        
    finally:
        await close_mongo_connection()


@celery_app.task(name="app.tasks.scraper_tasks.generate_daily_stats")
def generate_daily_stats():
    """Generate daily statistics"""
    try:
        logger.info("Starting daily stats generation")
        
        result = asyncio.run(_async_generate_stats())
        
        return {
            "status": "completed",
            "stats": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Stats generation task failed: {e}")
        raise


async def _async_generate_stats():
    """Async stats generation"""
    try:
        await connect_to_mongo()
        
        # Generate comprehensive stats
        stats = await AnnouncementService.get_announcement_stats()
        
        # Additional analytics can be added here
        # For example, save to a separate analytics collection
        
        logger.info(f"Generated daily stats: {stats.totalAnnouncements} total announcements")
        
        return stats.dict()
        
    finally:
        await close_mongo_connection()


@celery_app.task(name="app.tasks.scraper_tasks.export_announcements")
def export_announcements_task(
    format_type: str = "json",
    filters: Optional[dict] = None,
    max_records: int = 10000
):
    """Export announcements to various formats"""
    try:
        logger.info(f"Starting export task: format={format_type}, max_records={max_records}")
        
        result = asyncio.run(_async_export_announcements(format_type, filters, max_records))
        
        return {
            "status": "completed",
            "format": format_type,
            "records_exported": result.get("count", 0),
            "file_path": result.get("file_path"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Export task failed: {e}")
        raise


async def _async_export_announcements(format_type: str, filters: Optional[dict], max_records: int):
    """Async export operations"""
    import json
    import csv
    from pathlib import Path
    
    try:
        await connect_to_mongo()
        
        from app.db.database import get_announcements_collection
        collection = await get_announcements_collection()
        
        # Build query
        query = filters or {}
        
        # Get announcements
        cursor = collection.find(query).limit(max_records).sort("datePublication", -1)
        announcements = await cursor.to_list(length=max_records)
        
        # Create export directory
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        if format_type.lower() == "json":
            file_path = export_dir / f"announcements_{timestamp}.json"
            
            # Convert ObjectId to string for JSON serialization
            for ann in announcements:
                ann["_id"] = str(ann["_id"])
                # Convert datetime objects
                for key, value in ann.items():
                    if isinstance(value, datetime):
                        ann[key] = value.isoformat()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(announcements, f, ensure_ascii=False, indent=2)
        
        elif format_type.lower() == "csv":
            file_path = export_dir / f"announcements_{timestamp}.csv"
            
            if announcements:
                fieldnames = list(announcements[0].keys())
                
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for ann in announcements:
                        # Convert ObjectId and datetime to string
                        row = {}
                        for key, value in ann.items():
                            if hasattr(value, '__str__'):
                                row[key] = str(value)
                            else:
                                row[key] = value
                        writer.writerow(row)
        
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
        
        logger.info(f"Exported {len(announcements)} announcements to {file_path}")
        
        return {
            "count": len(announcements),
            "file_path": str(file_path)
        }
        
    finally:
        await close_mongo_connection()


@celery_app.task(name="app.tasks.scraper_tasks.send_alert_notifications")
def send_alert_notifications():
    """Send notifications for expiring announcements or important updates"""
    try:
        logger.info("Starting alert notifications task")
        
        result = asyncio.run(_async_send_notifications())
        
        return {
            "status": "completed",
            "notifications_sent": result.get("count", 0),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Alert notifications task failed: {e}")
        raise


async def _async_send_notifications():
    """Send various notifications"""
    try:
        await connect_to_mongo()
        
        # Get expiring announcements (next 3 days)
        expiring = await AnnouncementService.get_expiring_announcements(days=3)
        
        # Here you would implement email/SMS notifications
        # For now, just log the alerts
        
        count = 0
        for announcement in expiring:
            logger.info(f"ALERT: Announcement {announcement.reference} expires soon")
            count += 1
        
        # Additional notification logic can be added here
        
        return {"count": count}
        
    finally:
        await close_mongo_connection()


# Task monitoring utilities
@celery_app.task(name="app.tasks.scraper_tasks.monitor_scraper_health")
def monitor_scraper_health():
    """Monitor scraper health and performance"""
    try:
        logger.info("Starting scraper health monitoring")
        
        result = asyncio.run(_async_monitor_health())
        
        return {
            "status": "completed",
            "health_check": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health monitoring task failed: {e}")
        raise


async def _async_monitor_health():
    """Check system health"""
    try:
        await connect_to_mongo()
        
        from app.db.database import ping_database
        
        # Check database health
        db_healthy = await ping_database()
        
        # Check recent scraping activity
        from app.db.database import get_announcements_collection
        collection = await get_announcements_collection()
        
        recent_count = await collection.count_documents({
            "createdAt": {"$gte": datetime.utcnow() - timedelta(hours=24)}
        })
        
        # Get scraper status
        status = await scraper_service.get_status()
        
        health_report = {
            "database_healthy": db_healthy,
            "recent_announcements_24h": recent_count,
            "scraper_running": status.isRunning,
            "last_scraper_run": status.lastRun.isoformat() if status.lastRun else None,
            "scraper_errors": len(status.errors),
        }
        
        # Log warnings for issues
        if not db_healthy:
            logger.warning("Database health check failed")
        
        if recent_count == 0:
            logger.warning("No announcements scraped in the last 24 hours")
        
        if len(status.errors) > 0:
            logger.warning(f"Scraper has {len(status.errors)} recent errors")
        
        return health_report
        
    finally:
        await close_mongo_connection()


# Utility task for manual operations
@celery_app.task(name="app.tasks.scraper_tasks.reindex_announcements")
def reindex_announcements_task():
    """Reindex all announcements for better search performance"""
    try:
        logger.info("Starting announcement reindexing")
        
        result = asyncio.run(_async_reindex_announcements())
        
        return {
            "status": "completed",
            "reindexed_count": result.get("count", 0),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Reindexing task failed: {e}")
        raise


async def _async_reindex_announcements():
    """Reindex announcements"""
    try:
        await connect_to_mongo()
        
        from app.db.database import create_indexes, get_announcements_collection
        
        # Recreate indexes
        await create_indexes()
        
        # Get total count
        collection = await get_announcements_collection()
        total_count = await collection.count_documents({})
        
        logger.info(f"Reindexed {total_count} announcements")
        
        return {"count": total_count}
        
    finally:
        await close_mongo_connection()

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import Optional

from app.models.announcement import (
    ScraperStatus,
    ScraperConfig,
    UserInDB
)
from app.services.auth import require_admin
from app.services.scraper import scraper_service
from loguru import logger

router = APIRouter()


async def run_scraper_task(max_pages: Optional[int] = None, config: Optional[ScraperConfig] = None):
    """Background task to run scraper"""
    try:
        await scraper_service.scrape_pages(max_pages=max_pages, config=config)
    except Exception as e:
        logger.error(f"Background scraper task error: {e}")


@router.get("/status", response_model=ScraperStatus)
async def get_scraper_status():
    """Get current scraper status"""
    return await scraper_service.get_status()


@router.post("/start")
async def start_scraper(
    background_tasks: BackgroundTasks,
    max_pages: Optional[int] = None,
    start_page: int = 1,
    current_user: UserInDB = Depends(require_admin())
):
    """Start scraping process (Admin only)"""
    try:
        # Check if already running
        status = await scraper_service.get_status()
        if status.isRunning:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Scraper is already running"
            )
        
        # Create config
        config = ScraperConfig(
            maxPages=max_pages,
            startPage=start_page,
            enabled=True
        )
        
        # Start background task
        background_tasks.add_task(run_scraper_task, max_pages, config)
        
        return {
            "message": "Scraper started successfully",
            "maxPages": max_pages,
            "startPage": start_page
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting scraper: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not start scraper"
        )


@router.post("/stop")
async def stop_scraper(current_user: UserInDB = Depends(require_admin())):
    """Stop scraping process (Admin only)"""
    try:
        stopped = await scraper_service.stop_scraping()
        
        if stopped:
            return {"message": "Scraper stopped successfully"}
        else:
            return {"message": "Scraper was not running"}
            
    except Exception as e:
        logger.error(f"Error stopping scraper: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not stop scraper"
        )


@router.post("/schedule")
async def schedule_scraper(
    interval_hours: int = 24,
    current_user: UserInDB = Depends(require_admin())
):
    """Schedule automatic scraping (Admin only)"""
    try:
        if interval_hours < 1 or interval_hours > 168:  # Max 1 week
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Interval must be between 1 and 168 hours"
            )
        
        scheduled = await scraper_service.schedule_scraping(interval_hours)
        
        if scheduled:
            return {
                "message": "Scraper scheduled successfully",
                "intervalHours": interval_hours
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not schedule scraper"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling scraper: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not schedule scraper"
        )


@router.post("/test")
async def test_scraper(
    pages: int = 1,
    current_user: UserInDB = Depends(require_admin())
):
    """Test scraper with limited pages (Admin only)"""
    try:
        if pages < 1 or pages > 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Test pages must be between 1 and 5"
            )
        
        # Check if already running
        status = await scraper_service.get_status()
        if status.isRunning:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Scraper is already running"
            )
        
        # Run test scraping
        config = ScraperConfig(
            maxPages=pages,
            startPage=1,
            delayBetweenRequests=1,  # Faster for testing
            enabled=True
        )
        
        result = await scraper_service.scrape_pages(max_pages=pages, config=config)
        
        return {
            "message": "Test scraping completed",
            "result": result.dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in test scraping: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Test scraping failed"
        )


@router.get("/config", response_model=ScraperConfig)
async def get_scraper_config(current_user: UserInDB = Depends(require_admin())):
    """Get current scraper configuration (Admin only)"""
    try:
        # Load from state file or return defaults
        state = scraper_service.load_state()
        
        return ScraperConfig(
            maxPages=state.get("max_pages"),
            startPage=state.get("start_page", 1),
            delayBetweenRequests=state.get("delay_between_requests", 2),
            enabled=state.get("enabled", True)
        )
        
    except Exception as e:
        logger.error(f"Error getting scraper config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not get scraper configuration"
        )


@router.put("/config")
async def update_scraper_config(
    config: ScraperConfig,
    current_user: UserInDB = Depends(require_admin())
):
    """Update scraper configuration (Admin only)"""
    try:
        # Validate config
        if config.maxPages and (config.maxPages < 1 or config.maxPages > 1000):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Max pages must be between 1 and 1000"
            )
        
        if config.startPage < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start page must be at least 1"
            )
        
        if config.delayBetweenRequests < 1 or config.delayBetweenRequests > 60:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Delay between requests must be between 1 and 60 seconds"
            )
        
        # Save config to state
        state = scraper_service.load_state()
        state.update({
            "max_pages": config.maxPages,
            "start_page": config.startPage,
            "delay_between_requests": config.delayBetweenRequests,
            "enabled": config.enabled
        })
        scraper_service.save_state(state)
        
        return {
            "message": "Scraper configuration updated successfully",
            "config": config.dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating scraper config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update scraper configuration"
        )


@router.delete("/reset")
async def reset_scraper_state(current_user: UserInDB = Depends(require_admin())):
    """Reset scraper state and configuration (Admin only)"""
    try:
        # Check if running
        status = await scraper_service.get_status()
        if status.isRunning:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot reset while scraper is running. Stop scraper first."
            )
        
        # Reset state
        scraper_service.save_state({})
        
        # Reset current status
        scraper_service.current_status = ScraperStatus(
            isRunning=False,
            lastRun=None,
            nextRun=None,
            lastScrapedPages=0,
            totalAnnouncementsScraped=0,
            errors=[]
        )
        
        return {"message": "Scraper state reset successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting scraper state: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not reset scraper state"
        )

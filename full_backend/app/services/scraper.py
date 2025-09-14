import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
import requests
from lxml import html

from app.core.config import settings
from app.services.announcement import AnnouncementService
from app.models.announcement import ScraperStatus, ScraperConfig
from app.db.database import get_database


class ScraperService:
    def __init__(self):
        self.session = requests.Session()
        self.is_running = False
        self.current_status = ScraperStatus(
            isRunning=False,
            lastRun=None,
            nextRun=None,
            lastScrapedPages=0,
            totalAnnouncementsScraped=0,
            errors=[]
        )
        self.state_file = Path("scraper_state.json")
        
    def extract_prado_state(self, tree) -> Optional[str]:
        """Extract PRADO state from HTML tree"""
        for name in ("PRADO_PAGESTATE", "PRADO_PAGE_STATE"):
            try:
                val = tree.xpath(f'//input[@name="{name}"]/@value')
                if val:
                    return val[0]
            except Exception:
                continue
        return None
    
    async def fetch_page(self, url: str, page_num: int = 1, prado_state: str = None) -> tuple:
        """Fetch page with retry logic"""
        for attempt in range(1, settings.SCRAPER_MAX_RETRIES + 1):
            try:
                headers = {"User-Agent": settings.SCRAPER_USER_AGENT}
                
                if page_num == 1:
                    resp = self.session.get(
                        url, 
                        headers=headers, 
                        timeout=settings.SCRAPER_REQUEST_TIMEOUT
                    )
                else:
                    # PRADO postback for pagination
                    data = {
                        "PRADO_PAGESTATE": prado_state or "",
                        "PRADO_POSTBACK_TARGET": settings.PAGER_TARGET,
                        "PRADO_POSTBACK_PARAMETER": "",
                        settings.NUM_PAGE_FIELD: str(page_num),
                    }
                    resp = self.session.post(
                        url, 
                        headers=headers, 
                        data=data, 
                        timeout=settings.SCRAPER_REQUEST_TIMEOUT
                    )
                
                resp.raise_for_status()
                tree = html.fromstring(resp.content)
                
                # Add delay between requests
                await asyncio.sleep(settings.SCRAPER_DELAY_BETWEEN_REQUESTS)
                
                return resp, tree
                
            except Exception as e:
                logger.warning(f"Attempt {attempt}: Error fetching page {page_num}: {e}")
                if attempt < settings.SCRAPER_MAX_RETRIES:
                    await asyncio.sleep(2 * attempt)
        
        logger.error(f"Failed to fetch page {page_num} after {settings.SCRAPER_MAX_RETRIES} attempts")
        return None, None
    
    def extract_announcements_from_tree(self, tree) -> List[Dict]:
        """Extract announcements from HTML tree"""
        from app.scraper.extraction import extract_announcements_from_tree
        return extract_announcements_from_tree(tree)
    
    def save_state(self, state: Dict):
        """Save scraper state to file"""
        try:
            self.state_file.write_text(json.dumps(state, default=str, indent=2))
        except Exception as e:
            logger.error(f"Error saving scraper state: {e}")
    
    def load_state(self) -> Dict:
        """Load scraper state from file"""
        try:
            if self.state_file.exists():
                return json.loads(self.state_file.read_text())
        except Exception as e:
            logger.error(f"Error loading scraper state: {e}")
        return {}
    
    async def scrape_pages(
        self, 
        max_pages: Optional[int] = None, 
        start_page: int = 1,
        config: Optional[ScraperConfig] = None
    ) -> ScraperStatus:
        """Main scraping function"""
        if self.is_running:
            raise ValueError("Scraper is already running")
        
        self.is_running = True
        self.current_status.isRunning = True
        self.current_status.errors = []
        start_time = datetime.utcnow()
        
        try:
            # Load previous state
            state = self.load_state()
            current_page = state.get("current_page", start_page)
            prado_state = state.get("prado_state", None)
            
            # Apply config if provided
            if config:
                max_pages = config.maxPages or max_pages
                current_page = config.startPage or current_page
                if hasattr(settings, 'SCRAPER_DELAY_BETWEEN_REQUESTS'):
                    settings.SCRAPER_DELAY_BETWEEN_REQUESTS = config.delayBetweenRequests
            
            logger.info(f"Starting scraper from page {current_page}")
            
            # Fetch first page to get initial PRADO state
            resp, tree = await self.fetch_page(settings.BASE_URL, page_num=1)
            if tree is None:
                raise Exception("Failed to fetch initial page")
            
            prado_state = self.extract_prado_state(tree) or prado_state
            
            # Estimate total pages if possible
            total_pages = None
            try:
                pages_raw = tree.xpath('//input[@name="totalPages"]/@value')
                if pages_raw:
                    total_pages = int(pages_raw[0])
            except Exception:
                pass
            
            page = current_page
            pages_scraped = 0
            total_announcements = 0
            
            while True:
                if max_pages and pages_scraped >= max_pages:
                    logger.info(f"Reached max_pages={max_pages}. Stopping.")
                    break
                
                logger.info(f"Scraping page {page}")
                
                resp, tree = await self.fetch_page(settings.BASE_URL, page_num=page, prado_state=prado_state)
                if tree is None:
                    error_msg = f"Failed to fetch page {page}"
                    self.current_status.errors.append(error_msg)
                    logger.error(error_msg)
                    break
                
                # Update PRADO state
                new_prado_state = self.extract_prado_state(tree)
                if new_prado_state:
                    prado_state = new_prado_state
                
                # Extract announcements
                announcements = self.extract_announcements_from_tree(tree)
                
                if not announcements:
                    logger.warning(f"No announcements found on page {page}")
                    # Check if we've reached the end
                    if pages_scraped > 0:  # At least one page was successfully scraped
                        break
                
                # Save to database
                try:
                    inserted = await AnnouncementService.bulk_upsert_announcements(announcements)
                    total_announcements += inserted
                    logger.info(f"Page {page}: {len(announcements)} announcements extracted, {inserted} saved")
                except Exception as e:
                    error_msg = f"Error saving announcements from page {page}: {e}"
                    self.current_status.errors.append(error_msg)
                    logger.error(error_msg)
                
                # Save state
                self.save_state({
                    "current_page": page + 1,
                    "prado_state": prado_state,
                    "last_run": datetime.utcnow().isoformat(),
                    "total_pages": total_pages
                })
                
                pages_scraped += 1
                
                # Check stopping conditions
                if total_pages and page >= total_pages:
                    logger.info(f"Reached total_pages={total_pages}. Stopping.")
                    break
                
                page += 1
                
                # Update current status
                self.current_status.lastScrapedPages = pages_scraped
                self.current_status.totalAnnouncementsScraped = total_announcements
            
            # Final status update
            self.current_status.lastRun = start_time
            self.current_status.lastScrapedPages = pages_scraped
            self.current_status.totalAnnouncementsScraped = total_announcements
            
            logger.info(f"Scraping completed: {pages_scraped} pages, {total_announcements} announcements")
            
        except Exception as e:
            error_msg = f"Scraper error: {str(e)}"
            self.current_status.errors.append(error_msg)
            logger.error(error_msg)
        
        finally:
            self.is_running = False
            self.current_status.isRunning = False
            
        return self.current_status
    
    async def get_status(self) -> ScraperStatus:
        """Get current scraper status"""
        # Load state from file
        state = self.load_state()
        
        if "last_run" in state:
            try:
                self.current_status.lastRun = datetime.fromisoformat(state["last_run"])
            except Exception:
                pass
        
        return self.current_status
    
    async def stop_scraping(self) -> bool:
        """Stop the scraping process"""
        if self.is_running:
            self.is_running = False
            self.current_status.isRunning = False
            logger.info("Scraping stopped by user request")
            return True
        return False
    
    async def schedule_scraping(self, interval_hours: int = 24) -> bool:
        """Schedule automatic scraping"""
        try:
            # This would integrate with Celery or similar task queue
            # For now, just set next run time
            next_run = datetime.utcnow() + timedelta(hours=interval_hours)
            self.current_status.nextRun = next_run
            
            # Save to state
            state = self.load_state()
            state["next_scheduled_run"] = next_run.isoformat()
            state["schedule_interval_hours"] = interval_hours
            self.save_state(state)
            
            logger.info(f"Scraping scheduled for {next_run}")
            return True
            
        except Exception as e:
            logger.error(f"Error scheduling scraping: {e}")
            return False


# Global scraper instance
scraper_service = ScraperService()

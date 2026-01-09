import asyncio
import random
import traceback
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.config import (
    MIN_COMPETITOR_DELAY,
    MAX_COMPETITOR_DELAY,
    MAX_RETRIES,
    LOGS_DIR,
)
from src.models import (
    SessionLocal,
    Competitor,
    Ad,
    AdSnapshot,
    ScrapeRun,
    ScrapeError,
)
from src.scrapers.ad_library_scraper import AdLibraryScraper
from src.utils.media_downloader import MediaDownloader
from src.utils.logger import get_logger

logger = get_logger("orchestrator")


class ScrapeOrchestrator:
    """Orchestrates the full scraping process."""

    def __init__(self, run_type: str = "full", metadata: dict = None):
        self.run_type = run_type
        self.metadata = metadata or {}
        self.scraper = AdLibraryScraper()
        self.downloader = MediaDownloader()
        self.db: Optional[Session] = None
        self.scrape_run: Optional[ScrapeRun] = None

    async def run(self, competitor_id: str = None):
        """Run the scraping process."""
        self.db = SessionLocal()

        try:
            # Create scrape run record
            self.scrape_run = ScrapeRun(
                run_type=self.run_type,
                status="running",
                run_metadata=self.metadata
            )
            self.db.add(self.scrape_run)
            self.db.commit()

            logger.info(
                "scrape_run_started",
                run_id=self.scrape_run.id,
                run_type=self.run_type
            )

            # Start browser and downloader
            await self.scraper.start()
            await self.downloader.start()

            # Get competitors to scrape
            competitors = self._get_competitors(competitor_id)
            self.scrape_run.competitors_total = len(competitors)
            self.db.commit()

            logger.info("competitors_to_scrape", count=len(competitors))

            # Process each competitor
            for i, competitor in enumerate(competitors):
                try:
                    await self._process_competitor(competitor)
                    self.scrape_run.competitors_processed += 1
                except Exception as e:
                    self.scrape_run.competitors_failed += 1
                    logger.error(
                        "competitor_failed",
                        page_id=competitor.page_id,
                        error=str(e)
                    )

                self.db.commit()

                # Delay between competitors (except for last one)
                if i < len(competitors) - 1:
                    delay = random.uniform(MIN_COMPETITOR_DELAY, MAX_COMPETITOR_DELAY)
                    logger.info("waiting_between_competitors", delay=delay)
                    await asyncio.sleep(delay)

            # Mark run as completed
            self.scrape_run.mark_completed()
            self.db.commit()

            logger.info(
                "scrape_run_completed",
                run_id=self.scrape_run.id,
                competitors_processed=self.scrape_run.competitors_processed,
                ads_found=self.scrape_run.ads_found,
                ads_new=self.scrape_run.ads_new
            )

        except Exception as e:
            logger.error("scrape_run_failed", error=str(e))
            if self.scrape_run:
                self.scrape_run.mark_failed()
                self.db.commit()
            raise

        finally:
            await self.scraper.stop()
            await self.downloader.stop()
            if self.db:
                self.db.close()

    def _get_competitors(self, competitor_id: str = None) -> list[Competitor]:
        """Get list of competitors to scrape."""
        query = self.db.query(Competitor).filter(Competitor.is_active == True)

        if competitor_id:
            query = query.filter(Competitor.page_id == competitor_id)

        return query.all()

    async def _process_competitor(self, competitor: Competitor):
        """Process a single competitor with retries."""
        page_id = competitor.page_id
        logger.info("processing_competitor", page_id=page_id, name=competitor.page_name)

        for attempt in range(MAX_RETRIES):
            try:
                # Scrape ads
                ads_data = await self.scraper.scrape_competitor(page_id)
                self.scrape_run.ads_found += len(ads_data)

                # Process scraped ads
                await self._process_ads(page_id, ads_data)

                # Detect deleted ads
                deleted_count = self._detect_deleted_ads(page_id, ads_data)
                self.scrape_run.ads_deleted += deleted_count

                logger.info(
                    "competitor_processed",
                    page_id=page_id,
                    ads_found=len(ads_data),
                    deleted=deleted_count
                )
                return

            except Exception as e:
                logger.warning(
                    "competitor_attempt_failed",
                    page_id=page_id,
                    attempt=attempt + 1,
                    max_retries=MAX_RETRIES,
                    error=str(e)
                )

                # Save error with screenshot
                await self._save_error(page_id, e, attempt + 1)

                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(5)  # Brief delay before retry
                else:
                    raise

    async def _process_ads(self, page_id: str, ads_data: list[dict]):
        """Process and save scraped ads."""
        today = date.today()
        new_ads = []

        for ad_data in ads_data:
            ad_id = ad_data.get("ad_id")
            if not ad_id:
                continue

            # Check if ad exists
            existing_ad = self.db.query(Ad).filter(Ad.ad_id == ad_id).first()

            if existing_ad:
                # Update existing ad
                self._update_ad(existing_ad, ad_data)
                self.scrape_run.ads_updated += 1
            else:
                # Create new ad
                new_ad = self._create_ad(ad_data)
                self.db.add(new_ad)
                new_ads.append(ad_data)
                self.scrape_run.ads_new += 1

            # Create snapshot - convert dates to strings for JSON serialization
            raw_data_json = self._serialize_for_json(ad_data)
            snapshot = AdSnapshot(
                ad_id=ad_id,
                snapshot_date=today,
                scrape_run_id=self.scrape_run.id,
                is_active=ad_data.get("is_active", True),
                has_low_impressions=ad_data.get("has_low_impressions", False),
                ad_text=ad_data.get("ad_text"),
                media_url=ad_data.get("media_url"),
                landing_page_url=ad_data.get("landing_page_url"),
                platforms=ad_data.get("platforms"),
                regions=ad_data.get("regions"),
                raw_data=raw_data_json
            )
            self.db.add(snapshot)

        self.db.commit()

        # Download media for new ads
        if new_ads:
            await self._download_media_for_ads(new_ads)

    def _create_ad(self, ad_data: dict) -> Ad:
        """Create a new Ad record from scraped data."""
        return Ad(
            ad_id=ad_data["ad_id"],
            page_id=ad_data["page_id"],
            page_name=ad_data.get("page_name"),
            ad_text=ad_data.get("ad_text"),
            started_running_on=ad_data.get("started_running_on"),
            is_active=ad_data.get("is_active", True),
            has_low_impressions=ad_data.get("has_low_impressions", False),
            media_type=ad_data.get("media_type"),
            media_url=ad_data.get("media_url"),
            thumbnail_url=ad_data.get("thumbnail_url"),
            cta_type=ad_data.get("cta_type"),
            landing_page_url=ad_data.get("landing_page_url"),
            platforms=ad_data.get("platforms", []),
            regions=ad_data.get("regions", []),
        )

    def _update_ad(self, ad: Ad, ad_data: dict):
        """Update an existing Ad record."""
        ad.last_seen_at = datetime.utcnow()
        ad.is_active = ad_data.get("is_active", True)
        ad.has_low_impressions = ad_data.get("has_low_impressions", False)
        ad.ad_text = ad_data.get("ad_text") or ad.ad_text
        ad.media_url = ad_data.get("media_url") or ad.media_url
        ad.thumbnail_url = ad_data.get("thumbnail_url") or ad.thumbnail_url
        ad.landing_page_url = ad_data.get("landing_page_url") or ad.landing_page_url
        ad.platforms = ad_data.get("platforms") or ad.platforms
        ad.regions = ad_data.get("regions") or ad.regions
        ad.calculate_days_running()

    def _serialize_for_json(self, data: dict) -> dict:
        """Convert data to JSON-serializable format."""
        result = {}
        for key, value in data.items():
            if isinstance(value, date):
                result[key] = value.isoformat()
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = self._serialize_for_json(value)
            elif isinstance(value, list):
                result[key] = [
                    self._serialize_for_json(v) if isinstance(v, dict) else
                    v.isoformat() if isinstance(v, (date, datetime)) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def _detect_deleted_ads(self, page_id: str, current_ads: list[dict]) -> int:
        """Detect ads that were previously seen but not in current scrape."""
        current_ad_ids = {ad["ad_id"] for ad in current_ads if ad.get("ad_id")}

        # Find ads that were active but not in current scrape
        deleted_count = 0
        previous_ads = self.db.query(Ad).filter(
            Ad.page_id == page_id,
            Ad.is_active == True,
            Ad.ad_id.notin_(current_ad_ids) if current_ad_ids else True
        ).all()

        for ad in previous_ads:
            ad.is_active = False
            ad.last_seen_at = datetime.utcnow()
            deleted_count += 1
            logger.info("ad_marked_inactive", ad_id=ad.ad_id, page_id=page_id)

        return deleted_count

    async def _download_media_for_ads(self, ads: list[dict]):
        """Download media files for ads."""
        result = await self.downloader.download_batch(ads)
        self.scrape_run.media_downloaded += result["success"]

        # Update ads with local media paths
        for ad_data in ads:
            ad_id = ad_data.get("ad_id")
            if not ad_id:
                continue

            ad = self.db.query(Ad).filter(Ad.ad_id == ad_id).first()
            if ad:
                media_dir = self.downloader.get_media_dir(ad_data["page_id"], ad_id)
                ad.local_media_path = str(media_dir)
                ad.media_downloaded = True

        self.db.commit()

    async def _save_error(self, page_id: str, error: Exception, retry_count: int):
        """Save error details with screenshot."""
        # Take screenshot
        screenshot_dir = LOGS_DIR / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"{page_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        try:
            await self.scraper.take_screenshot(str(screenshot_path))
        except Exception:
            screenshot_path = None

        # Save error record
        scrape_error = ScrapeError(
            scrape_run_id=self.scrape_run.id,
            page_id=page_id,
            error_type=type(error).__name__,
            error_message=str(error),
            stack_trace=traceback.format_exc(),
            screenshot_path=str(screenshot_path) if screenshot_path else None,
            page_url=await self.scraper.get_current_url(),
            retry_count=retry_count
        )
        self.db.add(scrape_error)
        self.scrape_run.errors_count += 1
        self.db.commit()

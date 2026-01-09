import asyncio
import random
import re
from datetime import datetime, date
from typing import Optional
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from dateutil.parser import parse as parse_date

from src.config import (
    AD_LIBRARY_SEARCH_URL,
    HEADLESS,
    BROWSER_TIMEOUT,
    MIN_SCROLL_DELAY,
    MAX_SCROLL_DELAY,
    MEDIA_BASE_PATH,
)
from src.utils.logger import get_logger

logger = get_logger("ad_library_scraper")


class AdLibraryScraper:
    """Playwright-based scraper for Facebook Ad Library."""

    def __init__(self):
        self._playwright = None
        self.browser: Optional[Browser] = None
        self.context = None
        self.page: Optional[Page] = None

    async def start(self):
        """Start the browser instance."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ]
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self.page = await self.context.new_page()
        self.page.set_default_timeout(BROWSER_TIMEOUT)
        logger.info("browser_started", headless=HEADLESS)

    async def stop(self):
        """Stop the browser instance."""
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("browser_stopped")

    async def scrape_competitor(self, page_id: str) -> list[dict]:
        """Scrape all ads for a competitor from Ad Library."""
        url = AD_LIBRARY_SEARCH_URL.format(page_id=page_id)
        logger.info("scraping_competitor", page_id=page_id, url=url)

        try:
            await self.page.goto(url, wait_until="networkidle")
            await asyncio.sleep(2)  # Wait for initial load

            # Check if page exists
            if await self._check_no_results():
                logger.warning("no_ads_found", page_id=page_id)
                return []

            # Scroll to load all ads
            await self._scroll_to_load_all()

            # Extract ads
            ads = await self._extract_ads(page_id)
            logger.info("ads_extracted", page_id=page_id, count=len(ads))
            return ads

        except PlaywrightTimeout as e:
            logger.error("scrape_timeout", page_id=page_id, error=str(e))
            raise
        except Exception as e:
            logger.error("scrape_error", page_id=page_id, error=str(e))
            raise

    async def _check_no_results(self) -> bool:
        """Check if the page shows no results."""
        try:
            no_results = await self.page.query_selector('[role="main"] >> text=no ads')
            return no_results is not None
        except Exception:
            return False

    async def _scroll_to_load_all(self):
        """Scroll the page to load all ads (infinite scroll)."""
        logger.info("scrolling_to_load_ads")
        previous_height = 0
        no_change_count = 0
        max_no_change = 5  # More attempts to ensure all ads load
        scroll_count = 0
        max_scrolls = 50  # Safety limit

        while no_change_count < max_no_change and scroll_count < max_scrolls:
            scroll_count += 1

            # Scroll to bottom
            current_height = await self.page.evaluate("document.body.scrollHeight")
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

            # Random delay between scrolls
            delay = random.uniform(MIN_SCROLL_DELAY, MAX_SCROLL_DELAY)
            await asyncio.sleep(delay)

            # Check if new content loaded
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == previous_height:
                no_change_count += 1
            else:
                no_change_count = 0
            previous_height = new_height

            # Click "See more" buttons if present (every 3 scrolls)
            if scroll_count % 3 == 0:
                await self._click_see_more_buttons()

            # Log progress periodically
            if scroll_count % 10 == 0:
                logger.info("scroll_progress", scroll_count=scroll_count, height=new_height)

        logger.info("scrolling_complete", total_scrolls=scroll_count)

    async def _click_see_more_buttons(self):
        """Click any 'See more' buttons to expand ad text."""
        try:
            see_more_buttons = await self.page.query_selector_all('div[role="button"]:has-text("See more")')
            for button in see_more_buttons[:5]:  # Limit to avoid too many clicks
                try:
                    await button.click()
                    await asyncio.sleep(0.3)
                except Exception:
                    pass
        except Exception:
            pass

    async def _extract_ads(self, page_id: str) -> list[dict]:
        """Extract ad data from the loaded page."""
        ads = []

        # Primary selector: ad cards are direct children of the xrvj5dj container
        ad_containers = await self.page.query_selector_all('div.xrvj5dj > div.xh8yej3')

        # Fallback selectors if primary doesn't work
        if not ad_containers or len(ad_containers) < 2:
            ad_containers = await self.page.query_selector_all('div[class*="x1dr59a3"]')

        if not ad_containers or len(ad_containers) < 2:
            # Try finding by Library ID text content
            ad_containers = await self._find_ads_by_library_id()

        logger.info("found_ad_containers", count=len(ad_containers))

        for i, container in enumerate(ad_containers):
            try:
                ad_data = await self._extract_single_ad(container, page_id, i)
                if ad_data and ad_data.get("ad_id"):
                    ads.append(ad_data)
            except Exception as e:
                logger.warning("ad_extraction_failed", index=i, error=str(e))
                continue

        return ads

    async def _extract_single_ad(self, container, page_id: str, index: int) -> dict:
        """Extract data from a single ad container."""
        ad_data = {
            "ad_id": None,
            "page_id": page_id,
            "page_name": None,
            "ad_text": None,
            "started_running_on": None,
            "is_active": True,
            "has_low_impressions": False,
            "media_type": None,
            "media_url": None,
            "thumbnail_url": None,
            "cta_type": None,
            "landing_page_url": None,
            "platforms": [],
            "regions": [],
        }

        try:
            # Extract ad ID from "See ad details" link or data attribute
            ad_id = await self._extract_ad_id(container)
            if not ad_id:
                # No valid Library ID found - skip this container (it's not a real ad)
                logger.debug("skipping_invalid_container", index=index, reason="no_library_id")
                return None
            ad_data["ad_id"] = ad_id

            # Extract page name from the container text
            full_text = await container.inner_text()

            # Extract page name - usually the first line or from a link
            page_name_elem = await container.query_selector('a[href*="/ads/library/"] span')
            if page_name_elem:
                ad_data["page_name"] = await page_name_elem.inner_text()
            else:
                # Try to get from first significant text span
                first_span = await container.query_selector('span[dir="auto"]')
                if first_span:
                    name = await first_span.inner_text()
                    if name and len(name) < 100:
                        ad_data["page_name"] = name.strip()

            # Extract ad text - look for the main creative text
            # Usually this is before "Started running on" and after page name
            ad_data["ad_text"] = await self._extract_ad_text(container, full_text)

            # Extract started running date
            date_text = await self._extract_text_containing(container, "Started running on")
            if date_text:
                ad_data["started_running_on"] = self._parse_date(date_text)

            # Check if active
            inactive_text = await self._extract_text_containing(container, "Inactive")
            ad_data["is_active"] = inactive_text is None

            # Check for low impressions
            low_imp_text = await self._extract_text_containing(container, "impressions")
            ad_data["has_low_impressions"] = low_imp_text is not None and "low" in low_imp_text.lower()

            # Extract media type and URLs
            await self._extract_media_info(container, ad_data)

            # Extract CTA and landing page
            await self._extract_cta_info(container, ad_data)

            # Extract platforms
            platforms = await self._extract_platforms(container)
            ad_data["platforms"] = platforms

            # Extract regions
            regions = await self._extract_regions(container)
            ad_data["regions"] = regions

        except Exception as e:
            logger.warning("single_ad_extraction_error", index=index, error=str(e))

        return ad_data

    async def _find_ads_by_library_id(self) -> list:
        """Fallback: Find ad containers by looking for Library ID text."""
        try:
            # Use JavaScript to find ad cards by their content
            containers = await self.page.evaluate('''() => {
                const results = [];
                const allDivs = document.querySelectorAll('div');

                allDivs.forEach((div, idx) => {
                    const text = div.innerText || '';
                    // Check if this div contains exactly one Library ID (individual ad card)
                    const libraryIdMatches = text.match(/Library ID:/g);
                    if (libraryIdMatches && libraryIdMatches.length === 1 &&
                        text.includes('Started running on')) {
                        // Mark this div for selection
                        div.setAttribute('data-ad-card-idx', idx.toString());
                        results.push(idx);
                    }
                });
                return results;
            }''')

            # Now query for those marked elements
            ad_cards = []
            for idx in containers[:100]:  # Limit to 100 ads
                card = await self.page.query_selector(f'div[data-ad-card-idx="{idx}"]')
                if card:
                    ad_cards.append(card)

            return ad_cards
        except Exception as e:
            logger.warning("fallback_ad_search_failed", error=str(e))
            return []

    async def _extract_ad_id(self, container) -> Optional[str]:
        """Extract the ad ID (Library ID) from the container."""
        try:
            # Method 1: Look for Library ID in the text content
            text_content = await container.inner_text()
            if text_content:
                match = re.search(r'Library ID:\s*(\d+)', text_content)
                if match:
                    return match.group(1)

            # Method 2: Look for "See ad details" link
            details_link = await container.query_selector('a[href*="id="]')
            if details_link:
                href = await details_link.get_attribute("href")
                if href:
                    match = re.search(r'id=(\d+)', href)
                    if match:
                        return match.group(1)

            # Method 3: Try data attribute
            ad_id_attr = await container.get_attribute("data-ad-id")
            if ad_id_attr:
                return ad_id_attr

        except Exception:
            pass
        return None

    async def _extract_ad_text(self, container, full_text: str) -> Optional[str]:
        """Extract the main ad creative text."""
        try:
            # Method 1: Try to find text before "Started running on"
            if full_text and "Started running on" in full_text:
                parts = full_text.split("Started running on")
                if parts[0]:
                    # Remove common prefixes and clean up
                    text = parts[0].strip()
                    # Remove page name if it's at the start (usually first line)
                    lines = text.split('\n')
                    if len(lines) > 1:
                        # Skip header lines and get creative content
                        creative_lines = [l.strip() for l in lines[1:] if l.strip() and len(l.strip()) > 10]
                        if creative_lines:
                            return '\n'.join(creative_lines[:5])  # Limit to first 5 lines

            # Method 2: Look for span elements with substantial text
            text_spans = await container.query_selector_all('span[dir="auto"]')
            for span in text_spans:
                text = await span.inner_text()
                # Look for text that's likely ad copy (longer content, not metadata)
                if text and len(text) > 50 and "Library ID" not in text and "Started running" not in text:
                    return text[:1000]  # Limit length

        except Exception as e:
            logger.debug("ad_text_extraction_failed", error=str(e))

        return None

    async def _extract_text_containing(self, container, text: str) -> Optional[str]:
        """Find element containing specific text and return full text."""
        try:
            elems = await container.query_selector_all("span, div")
            for elem in elems:
                content = await elem.inner_text()
                if text.lower() in content.lower():
                    return content
        except Exception:
            pass
        return None

    def _parse_date(self, date_text: str) -> Optional[date]:
        """Parse date from text like 'Started running on Dec 15, 2023'."""
        try:
            # Extract date part
            match = re.search(r'(\w+\s+\d+,?\s*\d{4})', date_text)
            if match:
                return parse_date(match.group(1)).date()

            # Try other patterns
            match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', date_text)
            if match:
                return parse_date(match.group(1)).date()
        except Exception:
            pass
        return None

    async def _extract_media_info(self, container, ad_data: dict):
        """Extract media type and URLs."""
        try:
            # Check for video
            video_elem = await container.query_selector("video")
            if video_elem:
                ad_data["media_type"] = "VIDEO"
                ad_data["media_url"] = await video_elem.get_attribute("src")
                poster = await video_elem.get_attribute("poster")
                if poster:
                    ad_data["thumbnail_url"] = poster
                return

            # Check for carousel (multiple images)
            carousel_items = await container.query_selector_all('div[class*="carousel"] img, div[class*="scroll"] img')
            if len(carousel_items) > 1:
                ad_data["media_type"] = "CAROUSEL"
                # Get first image URL
                if carousel_items:
                    ad_data["media_url"] = await carousel_items[0].get_attribute("src")
                return

            # Check for single image
            img_elem = await container.query_selector("img[src*='scontent']")
            if img_elem:
                ad_data["media_type"] = "IMAGE"
                ad_data["media_url"] = await img_elem.get_attribute("src")
                ad_data["thumbnail_url"] = ad_data["media_url"]

        except Exception as e:
            logger.warning("media_extraction_error", error=str(e))

    async def _extract_cta_info(self, container, ad_data: dict):
        """Extract CTA button and landing page URL."""
        try:
            # Find CTA button
            cta_buttons = await container.query_selector_all('a[role="link"], a[class*="cta"]')
            for btn in cta_buttons:
                href = await btn.get_attribute("href")
                text = await btn.inner_text()

                # Filter out internal Facebook links
                if href and "facebook.com/ads/library" not in href:
                    ad_data["landing_page_url"] = href
                    if text:
                        ad_data["cta_type"] = text.strip()
                    break

        except Exception as e:
            logger.warning("cta_extraction_error", error=str(e))

    async def _extract_platforms(self, container) -> list[str]:
        """Extract platforms where the ad is shown."""
        platforms = []
        try:
            platform_text = await self._extract_text_containing(container, "Platforms")
            if platform_text:
                # Parse platform list
                if "Facebook" in platform_text:
                    platforms.append("Facebook")
                if "Instagram" in platform_text:
                    platforms.append("Instagram")
                if "Messenger" in platform_text:
                    platforms.append("Messenger")
                if "Audience Network" in platform_text:
                    platforms.append("Audience Network")
        except Exception:
            pass
        return platforms

    async def _extract_regions(self, container) -> list[str]:
        """Extract regions/countries where the ad is targeted."""
        regions = []
        try:
            # Look for "Location" or country info
            location_text = await self._extract_text_containing(container, "Location")
            if location_text:
                # Basic parsing - split by common separators
                parts = re.split(r'[,;]', location_text)
                for part in parts:
                    part = part.strip()
                    if part and len(part) < 50 and "Location" not in part:
                        regions.append(part)
        except Exception:
            pass
        return regions

    async def take_screenshot(self, path: str):
        """Take a screenshot for debugging."""
        try:
            await self.page.screenshot(path=path, full_page=True)
            logger.info("screenshot_saved", path=path)
        except Exception as e:
            logger.error("screenshot_failed", error=str(e))

    async def get_current_url(self) -> str:
        """Get the current page URL."""
        return self.page.url if self.page else ""

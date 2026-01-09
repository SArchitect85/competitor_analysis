import asyncio
import aiofiles
import httpx
from pathlib import Path
from urllib.parse import urlparse
import re

from src.config import MEDIA_BASE_PATH
from src.utils.logger import get_logger

logger = get_logger("media_downloader")


class MediaDownloader:
    """Download and store media files from ads."""

    def __init__(self, base_path: Path = None):
        self.base_path = base_path or MEDIA_BASE_PATH
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.client = None
        # URL deduplication cache: maps media_url -> local file path
        self._url_cache: dict[str, str] = {}

    async def start(self):
        """Initialize the HTTP client."""
        self.client = httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    async def stop(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()

    def get_media_dir(self, page_id: str, ad_id: str) -> Path:
        """Get the directory path for storing media for an ad."""
        media_dir = self.base_path / page_id / ad_id
        media_dir.mkdir(parents=True, exist_ok=True)
        return media_dir

    async def download_media(
        self,
        page_id: str,
        ad_id: str,
        media_url: str,
        thumbnail_url: str = None,
        media_type: str = "IMAGE"
    ) -> dict:
        """Download media and thumbnail for an ad."""
        result = {
            "success": False,
            "media_path": None,
            "thumbnail_path": None,
            "error": None,
            "deduplicated": False
        }

        if not media_url:
            result["error"] = "No media URL provided"
            return result

        # Check if we've already downloaded this media URL (deduplication)
        if media_url in self._url_cache:
            result["media_path"] = self._url_cache[media_url]
            result["success"] = True
            result["deduplicated"] = True
            logger.info("media_deduplicated", ad_id=ad_id, cached_path=result["media_path"])

            # Also check thumbnail cache
            if thumbnail_url and thumbnail_url in self._url_cache:
                result["thumbnail_path"] = self._url_cache[thumbnail_url]
            return result

        media_dir = self.get_media_dir(page_id, ad_id)

        try:
            # Download main media
            media_path = await self._download_file(
                media_url,
                media_dir,
                self._get_filename(media_url, media_type)
            )
            if media_path:
                result["media_path"] = str(media_path)
                # Cache the URL -> path mapping for deduplication
                self._url_cache[media_url] = str(media_path)

            # Download thumbnail if provided and different from media
            if thumbnail_url and thumbnail_url != media_url:
                # Check thumbnail cache first
                if thumbnail_url in self._url_cache:
                    result["thumbnail_path"] = self._url_cache[thumbnail_url]
                else:
                    thumb_path = await self._download_file(
                        thumbnail_url,
                        media_dir,
                        "thumbnail" + self._get_extension(thumbnail_url, "IMAGE")
                    )
                    if thumb_path:
                        result["thumbnail_path"] = str(thumb_path)
                        self._url_cache[thumbnail_url] = str(thumb_path)

            result["success"] = bool(result["media_path"])

        except Exception as e:
            logger.error(
                "media_download_failed",
                page_id=page_id,
                ad_id=ad_id,
                error=str(e)
            )
            result["error"] = str(e)

        return result

    async def _download_file(self, url: str, directory: Path, filename: str) -> Path:
        """Download a file from URL to the specified directory."""
        if not url or not url.startswith("http"):
            return None

        file_path = directory / filename

        try:
            logger.debug("downloading_file", url=url[:100], path=str(file_path))

            response = await self.client.get(url)
            response.raise_for_status()

            async with aiofiles.open(file_path, "wb") as f:
                await f.write(response.content)

            logger.info("file_downloaded", path=str(file_path), size=len(response.content))
            return file_path

        except httpx.HTTPStatusError as e:
            logger.warning("download_http_error", url=url[:100], status=e.response.status_code)
        except Exception as e:
            logger.warning("download_error", url=url[:100], error=str(e))

        return None

    def _get_filename(self, url: str, media_type: str) -> str:
        """Generate filename from URL and media type."""
        ext = self._get_extension(url, media_type)
        return f"media{ext}"

    def _get_extension(self, url: str, media_type: str) -> str:
        """Determine file extension from URL or media type."""
        # Try to extract from URL
        parsed = urlparse(url)
        path = parsed.path.lower()

        if ".mp4" in path:
            return ".mp4"
        elif ".webm" in path:
            return ".webm"
        elif ".jpg" in path or ".jpeg" in path:
            return ".jpg"
        elif ".png" in path:
            return ".png"
        elif ".gif" in path:
            return ".gif"
        elif ".webp" in path:
            return ".webp"

        # Fallback based on media type
        if media_type == "VIDEO":
            return ".mp4"
        else:
            return ".jpg"

    async def download_batch(
        self,
        ads: list[dict],
        concurrency: int = 3
    ) -> dict:
        """Download media for multiple ads with concurrency control."""
        results = {
            "total": len(ads),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "deduplicated": 0
        }

        semaphore = asyncio.Semaphore(concurrency)

        async def download_with_semaphore(ad):
            async with semaphore:
                if not ad.get("media_url"):
                    return {"skipped": True}
                return await self.download_media(
                    page_id=ad["page_id"],
                    ad_id=ad["ad_id"],
                    media_url=ad.get("media_url"),
                    thumbnail_url=ad.get("thumbnail_url"),
                    media_type=ad.get("media_type", "IMAGE")
                )

        tasks = [download_with_semaphore(ad) for ad in ads]
        download_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in download_results:
            if isinstance(result, Exception):
                results["failed"] += 1
            elif result.get("skipped"):
                results["skipped"] += 1
            elif result.get("success"):
                results["success"] += 1
                if result.get("deduplicated"):
                    results["deduplicated"] += 1
            else:
                results["failed"] += 1

        logger.info(
            "batch_download_complete",
            total=results["total"],
            success=results["success"],
            failed=results["failed"],
            skipped=results["skipped"],
            deduplicated=results["deduplicated"]
        )

        return results

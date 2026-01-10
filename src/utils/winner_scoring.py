"""Winner scoring algorithm for competitor ads.

Scores ads 0-100 based on multiple signals indicating success.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from collections import defaultdict
import hashlib
from typing import Optional

from src.models import Ad
from src.utils.logger import get_logger

logger = get_logger("winner_scoring")


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of how an ad's score was calculated."""
    days_running_score: int = 0
    active_score: int = 0
    impressions_score: int = 0
    media_type_score: int = 0
    landing_page_score: int = 0
    consistency_score: int = 0
    total: int = 0

    def to_dict(self) -> dict:
        return {
            "days_running": self.days_running_score,
            "active": self.active_score,
            "impressions": self.impressions_score,
            "media_type": self.media_type_score,
            "landing_page": self.landing_page_score,
            "consistency": self.consistency_score,
            "total": self.total,
        }


def calculate_winner_score(ad: Ad, snapshot_count: int = 1) -> tuple[int, ScoreBreakdown]:
    """
    Calculate winner score for an ad based on multiple signals.

    Scoring Criteria:
    - days_running >= 30: +25 points
    - days_running >= 60: +15 more points
    - days_running >= 90: +10 more points
    - is_active = true: +10 points
    - has_low_impressions = false: +15 points (healthy delivery)
    - has_low_impressions = true: -20 points (being throttled)
    - has_video (not image): +5 points
    - has_landing_page_url: +5 points
    - seen_in_multiple_snapshots: +15 points

    Returns:
        tuple of (score, breakdown)
    """
    breakdown = ScoreBreakdown()
    score = 0

    # Days running scoring (up to 50 points)
    days = ad.days_running or 0
    if days >= 30:
        breakdown.days_running_score += 25
    if days >= 60:
        breakdown.days_running_score += 15
    if days >= 90:
        breakdown.days_running_score += 10
    score += breakdown.days_running_score

    # Active status (+10 points)
    if ad.is_active:
        breakdown.active_score = 10
        score += 10

    # Impressions signal (+15 or -20 points)
    if ad.has_low_impressions:
        breakdown.impressions_score = -20
        score -= 20
    else:
        breakdown.impressions_score = 15
        score += 15

    # Media type (+5 for video)
    if ad.media_type and ad.media_type.upper() == "VIDEO":
        breakdown.media_type_score = 5
        score += 5

    # Landing page (+5 if present)
    if ad.landing_page_url:
        breakdown.landing_page_score = 5
        score += 5

    # Consistency/snapshots (+15 if seen multiple times)
    if snapshot_count > 1:
        breakdown.consistency_score = 15
        score += 15

    # Clamp score to 0-100
    score = max(0, min(100, score))
    breakdown.total = score

    return score, breakdown


def text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity ratio between two texts.

    Returns:
        Float between 0.0 and 1.0 (1.0 = identical)
    """
    if not text1 or not text2:
        return 0.0

    # Normalize texts
    text1 = text1.lower().strip()
    text2 = text2.lower().strip()

    if text1 == text2:
        return 1.0

    return SequenceMatcher(None, text1, text2).ratio()


def generate_media_hash(media_url: str) -> Optional[str]:
    """Generate a hash from media URL for deduplication."""
    if not media_url:
        return None

    # Extract the core part of the URL (ignore query params that change)
    # Facebook URLs often have the actual file identifier in the path
    url_parts = media_url.split("?")[0]  # Remove query params

    return hashlib.md5(url_parts.encode()).hexdigest()[:16]


def find_scaling_clusters(ads: list[Ad], similarity_threshold: float = 0.7) -> dict[str, list[str]]:
    """
    Find groups of similar ads that indicate scaling behavior.

    Scaling signals:
    - Multiple ads from same competitor with similar ad_text (>70% similarity)
    - Same video/thumbnail used across multiple ads

    Returns:
        Dict mapping cluster_id to list of ad_ids
    """
    clusters = {}
    ad_to_cluster = {}
    cluster_counter = 0

    # Group ads by competitor first
    by_competitor = defaultdict(list)
    for ad in ads:
        by_competitor[ad.page_id].append(ad)

    for page_id, competitor_ads in by_competitor.items():
        if len(competitor_ads) < 2:
            continue

        # Check for text similarity clusters
        for i, ad1 in enumerate(competitor_ads):
            if ad1.ad_id in ad_to_cluster:
                continue

            cluster_members = [ad1.ad_id]

            for ad2 in competitor_ads[i+1:]:
                if ad2.ad_id in ad_to_cluster:
                    continue

                # Check text similarity
                similarity = text_similarity(ad1.ad_text or "", ad2.ad_text or "")

                if similarity >= similarity_threshold:
                    cluster_members.append(ad2.ad_id)
                    continue

                # Check media URL similarity (same creative reused)
                if ad1.media_url and ad2.media_url:
                    hash1 = generate_media_hash(ad1.media_url)
                    hash2 = generate_media_hash(ad2.media_url)
                    if hash1 and hash2 and hash1 == hash2:
                        cluster_members.append(ad2.ad_id)

            if len(cluster_members) > 1:
                cluster_id = f"cluster_{page_id}_{cluster_counter}"
                cluster_counter += 1
                clusters[cluster_id] = cluster_members
                for ad_id in cluster_members:
                    ad_to_cluster[ad_id] = cluster_id

    return clusters


def score_all_ads(db_session) -> dict:
    """
    Score all ads in the database and update their winner_score.

    Returns:
        Summary statistics
    """
    from src.models import Ad, AdSnapshot
    from sqlalchemy import func

    # Get snapshot counts for each ad
    snapshot_counts = dict(
        db_session.query(AdSnapshot.ad_id, func.count(AdSnapshot.id))
        .group_by(AdSnapshot.ad_id)
        .all()
    )

    # Get all ads
    ads = db_session.query(Ad).all()

    stats = {
        "total_ads": len(ads),
        "scored": 0,
        "winners": 0,  # score >= 50
        "top_performers": 0,  # score >= 75
        "clusters_found": 0,
    }

    # Score each ad
    for ad in ads:
        snapshot_count = snapshot_counts.get(ad.ad_id, 1)
        ad.snapshot_count = snapshot_count

        score, breakdown = calculate_winner_score(ad, snapshot_count)
        ad.winner_score = score

        stats["scored"] += 1
        if score >= 50:
            stats["winners"] += 1
        if score >= 75:
            stats["top_performers"] += 1

        logger.debug("scored_ad", ad_id=ad.ad_id, score=score, breakdown=breakdown.to_dict())

    # Find scaling clusters
    clusters = find_scaling_clusters(ads)
    stats["clusters_found"] = len(clusters)

    # Update cluster IDs
    for cluster_id, ad_ids in clusters.items():
        for ad_id in ad_ids:
            ad = db_session.query(Ad).filter(Ad.ad_id == ad_id).first()
            if ad:
                ad.scaling_cluster_id = cluster_id

    db_session.commit()

    logger.info("scoring_complete", **stats)
    return stats

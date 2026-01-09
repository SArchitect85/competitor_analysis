#!/usr/bin/env python3
"""
View scrape run statistics and ad counts.

Usage:
    python scripts/view_stats.py
    python scripts/view_stats.py --runs 10
    python scripts/view_stats.py --ads --competitor {page_id}
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from sqlalchemy import func

from src.models import SessionLocal, Competitor, Ad, ScrapeRun, ScrapeError


@click.command()
@click.option("--runs", type=int, default=5, help="Number of recent runs to show")
@click.option("--ads", is_flag=True, help="Show ad statistics")
@click.option("--competitor", type=str, help="Filter by competitor page_id")
@click.option("--errors", is_flag=True, help="Show recent errors")
def main(runs: int, ads: bool, competitor: str, errors: bool):
    """View scraper statistics."""

    db = SessionLocal()

    try:
        if errors:
            show_errors(db)
        elif ads:
            show_ad_stats(db, competitor)
        else:
            show_run_stats(db, runs)
    finally:
        db.close()


def show_run_stats(db, limit: int):
    """Show recent scrape run statistics."""
    click.echo("\n=== Recent Scrape Runs ===\n")

    runs = db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(limit).all()

    if not runs:
        click.echo("No scrape runs found.")
        return

    for run in runs:
        duration = ""
        if run.completed_at and run.started_at:
            delta = run.completed_at - run.started_at
            duration = f" ({delta.seconds}s)"

        click.echo(f"Run #{run.id} [{run.run_type}] - {run.status}{duration}")
        click.echo(f"  Started: {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        click.echo(f"  Competitors: {run.competitors_processed}/{run.competitors_total} (failed: {run.competitors_failed})")
        click.echo(f"  Ads: found={run.ads_found}, new={run.ads_new}, updated={run.ads_updated}, deleted={run.ads_deleted}")
        click.echo(f"  Media downloaded: {run.media_downloaded}")
        click.echo(f"  Errors: {run.errors_count}")
        click.echo("")


def show_ad_stats(db, competitor_id: str = None):
    """Show ad statistics."""
    click.echo("\n=== Ad Statistics ===\n")

    query = db.query(Ad)
    if competitor_id:
        query = query.filter(Ad.page_id == competitor_id)

    total_ads = query.count()
    active_ads = query.filter(Ad.is_active == True).count()
    inactive_ads = query.filter(Ad.is_active == False).count()

    click.echo(f"Total ads: {total_ads}")
    click.echo(f"Active: {active_ads}")
    click.echo(f"Inactive: {inactive_ads}")

    # Media type breakdown
    click.echo("\nBy media type:")
    media_counts = db.query(
        Ad.media_type,
        func.count(Ad.id)
    ).group_by(Ad.media_type).all()

    for media_type, count in media_counts:
        click.echo(f"  {media_type or 'Unknown'}: {count}")

    # Ads by competitor
    if not competitor_id:
        click.echo("\nAds by competitor:")
        competitor_counts = db.query(
            Ad.page_id,
            Ad.page_name,
            func.count(Ad.id)
        ).group_by(Ad.page_id, Ad.page_name).order_by(func.count(Ad.id).desc()).limit(10).all()

        for page_id, name, count in competitor_counts:
            click.echo(f"  {name or page_id}: {count} ads")

    # Recent ads
    click.echo("\nMost recent ads:")
    recent = query.order_by(Ad.first_seen_at.desc()).limit(5).all()
    for ad in recent:
        click.echo(f"  [{ad.ad_id}] {ad.page_name} - {ad.first_seen_at.strftime('%Y-%m-%d')}")


def show_errors(db):
    """Show recent errors."""
    click.echo("\n=== Recent Errors ===\n")

    errors = db.query(ScrapeError).order_by(ScrapeError.created_at.desc()).limit(10).all()

    if not errors:
        click.echo("No errors found.")
        return

    for error in errors:
        click.echo(f"Error #{error.id} - Run #{error.scrape_run_id}")
        click.echo(f"  Page ID: {error.page_id}")
        click.echo(f"  Type: {error.error_type}")
        click.echo(f"  Message: {error.error_message[:100]}...")
        click.echo(f"  Retry count: {error.retry_count}")
        if error.screenshot_path:
            click.echo(f"  Screenshot: {error.screenshot_path}")
        click.echo("")


if __name__ == "__main__":
    main()

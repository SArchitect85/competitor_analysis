#!/usr/bin/env python3
"""
Facebook Ad Library Scraper - Main CLI Entry Point

Usage:
    python main.py                          # Run full scrape
    python main.py --backfill               # Deep historical scrape
    python main.py --competitor {page_id}   # Single competitor scrape
"""

import asyncio
import sys
import click

from src.models import init_db
from src.scrapers.orchestrator import ScrapeOrchestrator
from src.utils.logger import get_logger

logger = get_logger("main")


@click.command()
@click.option("--backfill", is_flag=True, help="Run deep historical scrape")
@click.option("--competitor", type=str, help="Scrape single competitor by page_id")
@click.option("--init-db", "initialize_db", is_flag=True, help="Initialize database tables")
def main(backfill: bool, competitor: str, initialize_db: bool):
    """Facebook Ad Library Scraper CLI."""

    if initialize_db:
        click.echo("Initializing database tables...")
        init_db()
        click.echo("Database initialized successfully!")
        return

    # Determine run type
    if competitor:
        run_type = "single"
        click.echo(f"Starting single competitor scrape: {competitor}")
    elif backfill:
        run_type = "backfill"
        click.echo("Starting backfill scrape...")
    else:
        run_type = "full"
        click.echo("Starting full scrape...")

    # Build metadata
    metadata = {
        "cli_args": {
            "backfill": backfill,
            "competitor": competitor
        }
    }

    # Run the scraper
    orchestrator = ScrapeOrchestrator(run_type=run_type, metadata=metadata)

    try:
        asyncio.run(orchestrator.run(competitor_id=competitor))
        click.echo("Scrape completed successfully!")
        sys.exit(0)
    except KeyboardInterrupt:
        click.echo("\nScrape interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error("scrape_failed", error=str(e))
        click.echo(f"Scrape failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

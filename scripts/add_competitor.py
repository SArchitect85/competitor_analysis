#!/usr/bin/env python3
"""
Add or manage competitors in the database.

Usage:
    python scripts/add_competitor.py --page-id {id} --name {name}
    python scripts/add_competitor.py --list
    python scripts/add_competitor.py --deactivate {page_id}
    python scripts/add_competitor.py --activate {page_id}
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from sqlalchemy.exc import IntegrityError

from src.models import SessionLocal, Competitor, init_db


@click.command()
@click.option("--page-id", type=str, help="Facebook Page ID to add")
@click.option("--name", type=str, help="Name of the competitor")
@click.option("--list", "list_competitors", is_flag=True, help="List all competitors")
@click.option("--deactivate", type=str, help="Deactivate a competitor by page_id")
@click.option("--activate", type=str, help="Activate a competitor by page_id")
@click.option("--delete", type=str, help="Delete a competitor by page_id")
@click.option("--init-db", "initialize_db", is_flag=True, help="Initialize database tables")
def main(
    page_id: str,
    name: str,
    list_competitors: bool,
    deactivate: str,
    activate: str,
    delete: str,
    initialize_db: bool
):
    """Manage competitors in the Facebook Ad Library scraper."""

    if initialize_db:
        click.echo("Initializing database tables...")
        init_db()
        click.echo("Database initialized successfully!")
        return

    db = SessionLocal()

    try:
        if list_competitors:
            list_all_competitors(db)
        elif deactivate:
            set_competitor_active(db, deactivate, False)
        elif activate:
            set_competitor_active(db, activate, True)
        elif delete:
            delete_competitor(db, delete)
        elif page_id and name:
            add_competitor(db, page_id, name)
        elif page_id:
            click.echo("Error: --name is required when adding a competitor")
            sys.exit(1)
        else:
            click.echo("Use --help for usage information")
            sys.exit(1)
    finally:
        db.close()


def add_competitor(db, page_id: str, name: str):
    """Add a new competitor."""
    try:
        competitor = Competitor(page_id=page_id, page_name=name)
        db.add(competitor)
        db.commit()
        click.echo(f"Added competitor: {name} (page_id: {page_id})")
    except IntegrityError:
        db.rollback()
        click.echo(f"Error: Competitor with page_id {page_id} already exists")
        sys.exit(1)


def list_all_competitors(db):
    """List all competitors."""
    competitors = db.query(Competitor).order_by(Competitor.page_name).all()

    if not competitors:
        click.echo("No competitors found. Add one with --page-id and --name")
        return

    click.echo(f"\n{'Page ID':<20} {'Name':<40} {'Active':<10}")
    click.echo("-" * 70)

    for c in competitors:
        status = "Yes" if c.is_active else "No"
        click.echo(f"{c.page_id:<20} {c.page_name:<40} {status:<10}")

    click.echo(f"\nTotal: {len(competitors)} competitors")


def set_competitor_active(db, page_id: str, active: bool):
    """Set competitor active status."""
    competitor = db.query(Competitor).filter(Competitor.page_id == page_id).first()

    if not competitor:
        click.echo(f"Error: Competitor with page_id {page_id} not found")
        sys.exit(1)

    competitor.is_active = active
    db.commit()

    status = "activated" if active else "deactivated"
    click.echo(f"Competitor {competitor.page_name} ({page_id}) has been {status}")


def delete_competitor(db, page_id: str):
    """Delete a competitor."""
    competitor = db.query(Competitor).filter(Competitor.page_id == page_id).first()

    if not competitor:
        click.echo(f"Error: Competitor with page_id {page_id} not found")
        sys.exit(1)

    name = competitor.page_name
    db.delete(competitor)
    db.commit()
    click.echo(f"Deleted competitor: {name} ({page_id})")


if __name__ == "__main__":
    main()

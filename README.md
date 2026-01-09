# Competitor Ad Tracker

A Python-based scraper and dashboard for tracking competitor ads from Facebook Ad Library.

## Features

- **Automated Scraping**: Playwright-based scraper that extracts ads from Facebook Ad Library
- **Media Downloads**: Automatically downloads ad images and videos locally
- **Change Detection**: Tracks ad snapshots over time to detect new, updated, and deleted ads
- **Deduplication**: Avoids re-downloading duplicate media files
- **Web Dashboard**: Streamlit-based dashboard for viewing and analyzing ads
- **Winner Detection**: Highlights ads running 30+ days as potential winners

## Installation

### Prerequisites

- Python 3.9+
- Chrome/Chromium browser

### Setup

```bash
# Clone the repository
git clone https://github.com/SArchitect85/competitor_analysis.git
cd competitor_analysis

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Copy environment file
cp .env.example .env
```

### Configuration

Edit `.env` file:

```env
# Database (SQLite for local, PostgreSQL for production)
DATABASE_URL=sqlite:///data/competitive.db

# Browser settings
HEADLESS=true
BROWSER_TIMEOUT=30000

# Rate limiting
MIN_COMPETITOR_DELAY=30
MAX_COMPETITOR_DELAY=60
MIN_SCROLL_DELAY=2
MAX_SCROLL_DELAY=5
MAX_RETRIES=3
```

## Usage

### Adding Competitors

```bash
python scripts/add_competitor.py <page_id> [--name "Company Name"]
```

Find the `page_id` from Facebook Ad Library URL:
```
https://www.facebook.com/ads/library/?view_all_page_id=123456789
                                                        ^^^^^^^^^
                                                        page_id
```

### Running the Scraper

```bash
# Full scrape of all competitors
python main.py

# Scrape a specific competitor
python main.py --competitor 123456789

# Backfill mode (all ads, not just active)
python main.py --backfill
```

### Viewing Statistics

```bash
python scripts/view_stats.py
```

### Web Dashboard

```bash
streamlit run dashboard.py --server.port 8501
```

Open http://localhost:8501 in your browser.

#### Dashboard Features

- **Overview**: Total ads, ads by competitor, media type breakdown
- **All Ads**: Sortable/filterable table with ad details
- **Winners**: Ads running 30+ days (potential winning creatives)
- **Ad Detail**: Full ad text, embedded media player, landing page URLs

## Project Structure

```
competitive/
├── main.py                 # CLI entry point
├── dashboard.py            # Streamlit web dashboard
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
├── src/
│   ├── config.py           # Configuration settings
│   ├── models/
│   │   ├── database.py     # SQLAlchemy setup
│   │   ├── competitor.py   # Competitor model
│   │   ├── ad.py           # Ad model
│   │   ├── snapshot.py     # AdSnapshot model
│   │   └── scrape_run.py   # ScrapeRun & ScrapeError models
│   ├── scrapers/
│   │   ├── ad_library_scraper.py  # Playwright scraper
│   │   └── orchestrator.py        # Scrape orchestration
│   └── utils/
│       ├── logger.py       # Structured logging
│       └── media_downloader.py    # Media download handler
├── scripts/
│   ├── add_competitor.py   # Add competitors
│   ├── view_stats.py       # View statistics
│   └── setup_ubuntu.sh     # Ubuntu/EC2 setup script
└── data/
    ├── competitive.db      # SQLite database
    └── media/              # Downloaded media files
        └── {page_id}/
            └── {ad_id}/
                ├── media.mp4
                └── thumbnail.jpg
```

## Database Schema

### Tables

- **competitors**: Facebook pages being tracked
- **ads**: Extracted ad data with media paths
- **ad_snapshots**: Daily snapshots of ad state
- **scrape_runs**: Execution history and stats
- **scrape_errors**: Error logs with screenshots

### Key Fields (ads)

| Field | Description |
|-------|-------------|
| ad_id | Facebook Library ID |
| page_id | Competitor's Facebook page ID |
| ad_text | Ad creative text |
| started_running_on | When the ad started |
| days_running | Calculated days active |
| media_type | VIDEO, IMAGE, or CAROUSEL |
| media_url | Original media URL |
| local_media_path | Downloaded media location |
| landing_page_url | Ad destination URL |
| is_active | Currently running |
| has_low_impressions | Low impression warning |

## Rate Limiting

The scraper includes built-in rate limiting to avoid detection:

- 30-60 second random delay between competitors
- 2-5 second delay between scroll actions
- Maximum 3 retries per competitor
- Human-like scrolling behavior

## License

MIT

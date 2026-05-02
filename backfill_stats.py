#!/usr/bin/env python3
"""Backfill weekly stats from a historical vault location."""

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    end_match = re.search(r'\n---\n', content[3:])
    if not end_match:
        return {}, content

    frontmatter_str = content[4:end_match.start() + 3]
    body = content[end_match.end() + 4:]

    frontmatter = {}
    current_key = None
    current_list = None
    lines = frontmatter_str.split('\n')

    for i, line in enumerate(lines):
        if not line.strip():
            continue

        if line.startswith('  - '):
            if current_list is not None:
                current_list.append(line[4:].strip().strip('"'))
            continue

        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip().strip('"')
            value = value.strip().strip('"')

            if value:
                frontmatter[key] = value
                current_key = None
                current_list = None
            else:
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if next_line.startswith('  - '):
                    frontmatter[key] = []
                    current_key = key
                    current_list = frontmatter[key]
                else:
                    frontmatter[key] = ""
                    current_key = None
                    current_list = None

    return frontmatter, body


def parse_date(date_str: str | None) -> datetime | None:
    """Parse a date string in YYYY-MM-DD format."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def collect_article_data(directory: Path) -> list[dict]:
    """Collect article metadata from a directory."""
    articles = []
    for md_file in directory.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(content)
        
        # Extract tags if present
        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        
        articles.append({
            "title": frontmatter.get("title", md_file.stem),
            "created": parse_date(frontmatter.get("created")),
            "date_read": parse_date(frontmatter.get("date-read")),
            "read_status": frontmatter.get("read-status", ""),
            "liked": frontmatter.get("liked", ""),
            "kats_kable": frontmatter.get("kats-kable", ""),
            "directory": directory.name,
        })
    return articles


def compute_weekly_stats(articles: list[dict], week_start: datetime, week_end: datetime) -> dict:
    """Compute weekly statistics from article data."""
    new_count = 0
    read_count = 0
    dnf_count = 0
    liked_count = 0
    kats_kable_count = 0
    
    for article in articles:
        # New articles: created this week
        if article["created"] and week_start <= article["created"] <= week_end:
            new_count += 1
        
        # Read articles: date-read this week
        if article["date_read"] and week_start <= article["date_read"] <= week_end:
            if article["read_status"] == "dnf":
                dnf_count += 1
            else:
                read_count += 1
            
            # Liked articles: read this week AND liked
            if article["liked"] in ("yes", "true", "1"):
                liked_count += 1
            
            # Kat's Kable articles: read this week AND has kats-kable set
            if article["kats_kable"] and article["kats_kable"] not in ("", "0", "no", "false"):
                kats_kable_count += 1
    
    # Inbox backlog: unread articles in Inbox (snapshot at end of week)
    inbox_unread = sum(1 for a in articles if a["directory"] == "Inbox" and a["read_status"] not in ("read", "yes"))
    
    # Archive total
    archive_total = sum(1 for a in articles if a["directory"] == "Archive")
    
    # DNF total
    dnf_total = sum(1 for a in articles if a["directory"] == "DNF")
    
    return {
        "new_count": new_count,
        "read_count": read_count,
        "dnf_count": dnf_count,
        "liked_count": liked_count,
        "kats_kable_count": kats_kable_count,
        "inbox_unread_count": inbox_unread,
        "archive_total": archive_total,
        "dnf_total": dnf_total,
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end": week_end.strftime("%Y-%m-%d"),
    }


def get_week_boundaries(reference_date: datetime) -> tuple[datetime, datetime]:
    """Return (week_start, week_end) for the week containing reference_date.
    Week starts on Sunday, ends on Saturday."""
    days_since_sunday = (reference_date.weekday() + 1) % 7
    week_start = reference_date - timedelta(days=days_since_sunday)
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    week_end = week_start + timedelta(days=6)
    week_end = week_end.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return week_start, week_end


def main():
    parser = argparse.ArgumentParser(description="Backfill weekly stats from historical vault")
    parser.add_argument("--data-dir", type=str, default="~/Dropbox/obsidian/reading-journal",
                        help="Path to vault with Inbox/ and Archive/ folders")
    parser.add_argument("--start-date", type=str, default="2026-01-26",
                        help="First Sunday to process (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None,
                        help="Last day to process (YYYY-MM-DD, default: today)")
    parser.add_argument("--output", type=str, default="weekly_stats_backfill.json",
                        help="Output JSON file path")
    args = parser.parse_args()
    
    # Resolve paths
    data_dir = Path(args.data_dir).expanduser()
    inbox_dir = data_dir / "Inbox"
    archive_dir = data_dir / "Archive"
    dnf_dir = data_dir / "DNF"
    
    if not inbox_dir.exists():
        print(f"Error: Inbox not found at {inbox_dir}")
        sys.exit(1)
    
    # Parse dates
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else datetime.now()
    
    print(f"Backfilling stats from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Data source: {data_dir}")
    
    # Collect all articles
    print("\nScanning articles...")
    inbox_articles = collect_article_data(inbox_dir)
    archive_articles = collect_article_data(archive_dir)
    dnf_articles = collect_article_data(dnf_dir) if dnf_dir.exists() else []
    all_articles = inbox_articles + archive_articles + dnf_articles
    
    print(f"  Inbox: {len(inbox_articles)} articles")
    print(f"  Archive: {len(archive_articles)} articles")
    print(f"  DNF: {len(dnf_articles)} articles")
    
    # Process each week
    weekly_data = {}
    current_week_start = start_date
    
    while current_week_start <= end_date:
        week_start, week_end = get_week_boundaries(current_week_start)
        week_key = week_start.strftime("%Y-W%W")
        
        stats = compute_weekly_stats(all_articles, week_start, week_end)
        weekly_data[week_key] = stats
        
        print(f"  {week_key}: New={stats['new_count']} Read={stats['read_count']} DNF={stats['dnf_count']} Liked={stats['liked_count']} Kable={stats['kats_kable_count']}")
        
        current_week_start = week_end + timedelta(days=1)
    
    # Save output
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(weekly_data, f, indent=2)
    
    print(f"\n✓ Backfill complete! Saved {len(weekly_data)} weeks to {output_path}")


if __name__ == "__main__":
    import sys
    main()

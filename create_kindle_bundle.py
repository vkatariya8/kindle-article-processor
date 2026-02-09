#!/usr/bin/env python3
"""Interactively bundle articles from Inbox into an epub for Kindle."""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

INBOX_DIR = Path(__file__).parent / "Inbox"
OUTPUT_DIR = Path(__file__).parent


def get_oldest_articles(count: int = 10) -> list[Path]:
    """Get the oldest N articles from Inbox, sorted by modification time."""
    articles = list(INBOX_DIR.glob("*.md"))
    articles.sort(key=lambda p: p.stat().st_mtime)
    return articles[:count]


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter and return (metadata dict, body content)."""
    if not content.startswith("---"):
        return {}, content

    end_match = re.search(r'\n---\n', content[3:])
    if not end_match:
        return {}, content

    frontmatter_str = content[4:end_match.start() + 3]
    body = content[end_match.end() + 4:]

    # Simple parsing for title and dates
    metadata = {}
    for line in frontmatter_str.split('\n'):
        if ':' in line and not line.startswith(' '):
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip().strip('"')
            if value:
                metadata[key] = value

    return metadata, body


def calculate_word_count(filepath: Path) -> int:
    """Calculate word count for article body (excluding frontmatter)."""
    content = filepath.read_text(encoding="utf-8")
    _, body = parse_frontmatter(content)
    return len(body.split())


def get_candidate_articles(filter_sent: bool = True) -> list[tuple[Path, dict]]:
    """Get candidate articles with metadata, sorted oldest first.

    Returns list of tuples: (filepath, metadata_dict)
    metadata_dict contains: title, word_count, date, mtime
    """
    articles = list(INBOX_DIR.glob("*.md"))

    candidates = []
    for article in articles:
        content = article.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)

        # Filter out already-sent articles if requested
        if filter_sent and metadata.get('sent-to-kindle') == 'yes':
            continue

        article_metadata = {
            'title': metadata.get('title', article.stem),
            'word_count': len(body.split()),
            'date': metadata.get('created') or metadata.get('published') or
                    datetime.fromtimestamp(article.stat().st_mtime).strftime("%Y-%m-%d"),
            'mtime': article.stat().st_mtime
        }
        candidates.append((article, article_metadata))

    # Sort by modification time (oldest first)
    candidates.sort(key=lambda x: x[1]['mtime'])
    return candidates


def display_article_selection_ui(candidates: list[tuple[Path, dict]], target_words: int) -> list[Path]:
    """Interactive CLI for selecting articles to bundle.

    Args:
        candidates: List of (filepath, metadata) tuples
        target_words: Target total word count

    Returns:
        List of selected article paths
    """
    # Display header with target information
    print("\n" + "="*80)
    print(f"KINDLE BUNDLE ARTICLE SELECTION")
    print(f"Target word count: {target_words:,} words")
    print(f"Tolerance: ±10% ({int(target_words * 0.9):,} - {int(target_words * 1.1):,} words)")
    print("="*80 + "\n")

    # Display available articles with numbering
    print(f"Available articles ({len(candidates)} total):\n")
    print(f"{'#':<4} {'Words':>8}  {'Date':<12}  {'Title':<50}")
    print("-" * 80)

    for idx, (filepath, meta) in enumerate(candidates, 1):
        title = meta['title'][:47] + "..." if len(meta['title']) > 50 else meta['title']
        print(f"{idx:<4} {meta['word_count']:>8,}  {meta['date']:<12}  {title}")

    # Interactive selection loop
    selected = []
    selected_words = 0

    print("\n" + "="*80)
    print("SELECTION INSTRUCTIONS:")
    print("  - Enter article numbers (space-separated) to add: e.g., '1 3 5'")
    print("  - Enter 'r <numbers>' to remove: e.g., 'r 3'")
    print("  - Enter 'done' to finish selection")
    print("  - Enter 'quit' to cancel")
    print("="*80 + "\n")

    while True:
        # Display current selection status
        if selected:
            print(f"\nCurrently selected: {len(selected)} articles, {selected_words:,} words")
            percentage = (selected_words / target_words) * 100
            print(f"Progress: {percentage:.1f}% of target")

            # Visual indicator
            if selected_words < target_words * 0.9:
                print("Status: Below target range (add more articles)")
            elif selected_words > target_words * 1.1:
                print("Status: Above target range (consider removing articles)")
            else:
                print("Status: Within target range ±10% ✓")
        else:
            print("\nNo articles selected yet.")

        # Get user input
        user_input = input("\nEnter selection: ").strip().lower()

        if user_input == 'done':
            if not selected:
                print("Error: No articles selected. Please select at least one article.")
                continue
            break

        if user_input == 'quit':
            print("Selection cancelled.")
            sys.exit(0)

        # Handle removal
        if user_input.startswith('r '):
            indices_str = user_input[2:].strip()
            try:
                indices = [int(x) for x in indices_str.split()]
                for idx in indices:
                    if idx < 1 or idx > len(candidates):
                        print(f"Error: Invalid article number {idx}")
                        continue
                    filepath = candidates[idx - 1][0]
                    if filepath in selected:
                        removed_words = candidates[idx - 1][1]['word_count']
                        selected.remove(filepath)
                        selected_words -= removed_words
                        print(f"Removed: {candidates[idx - 1][1]['title']} ({removed_words:,} words)")
                    else:
                        print(f"Article {idx} was not selected.")
            except ValueError:
                print("Error: Invalid input. Use format 'r <numbers>'")
            continue

        # Handle addition
        try:
            indices = [int(x) for x in user_input.split()]
            for idx in indices:
                if idx < 1 or idx > len(candidates):
                    print(f"Error: Invalid article number {idx}")
                    continue
                filepath = candidates[idx - 1][0]
                if filepath not in selected:
                    selected.append(filepath)
                    added_words = candidates[idx - 1][1]['word_count']
                    selected_words += added_words
                    print(f"Added: {candidates[idx - 1][1]['title']} ({added_words:,} words)")
                else:
                    print(f"Article {idx} already selected.")
        except ValueError:
            print("Error: Invalid input. Enter article numbers or 'done'/'quit'")

    print(f"\nFinal selection: {len(selected)} articles, {selected_words:,} words")
    return selected


def automatic_selection(candidates: list[tuple[Path, dict]], target_words: int, select_newest: bool = False) -> list[Path]:
    """Automatically select articles until reaching target word count.

    Args:
        candidates: List of (filepath, metadata) tuples sorted by age
        target_words: Target total word count
        select_newest: If True, select newest articles; otherwise oldest

    Returns:
        List of selected article paths
    """
    selected = []
    total_words = 0
    target_max = int(target_words * 1.1)  # Don't exceed 110% of target

    order = "newest" if select_newest else "oldest"
    print(f"Automatically selecting {order} articles to reach {target_words:,} words...\n")

    for filepath, meta in candidates:
        # Check if adding this article would exceed the max threshold
        if total_words + meta['word_count'] > target_max:
            # Only add if we haven't reached 90% yet
            if total_words < target_words * 0.9:
                selected.append(filepath)
                total_words += meta['word_count']
                print(f"  Added: {meta['title'][:60]} ({meta['word_count']:,} words)")
            break

        selected.append(filepath)
        total_words += meta['word_count']
        print(f"  Added: {meta['title'][:60]} ({meta['word_count']:,} words)")

        # Stop if we're within target range
        if total_words >= target_words * 0.9:
            break

    print(f"\nAutomatically selected: {len(selected)} articles, {total_words:,} words")
    percentage = (total_words / target_words) * 100
    print(f"Progress: {percentage:.1f}% of target")

    return selected


def get_article_date(filepath: Path) -> str:
    """Extract the created or published date from article frontmatter."""
    content = filepath.read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(content)
    return metadata.get('created') or metadata.get('published') or \
        datetime.fromtimestamp(filepath.stat().st_mtime).strftime("%Y-%m-%d")


def prepare_article_for_epub(filepath: Path) -> str:
    """Prepare article content for epub: strip frontmatter, add h1 title."""
    content = filepath.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(content)

    title = metadata.get('title', filepath.stem)

    # Demote all headings in body by one level to avoid chapter conflicts
    # (h1 -> h2, h2 -> h3, etc.)
    body = re.sub(r'^(#{1,5}) ', r'#\1 ', body, flags=re.MULTILINE)

    # Return content with h1 title as chapter heading
    return f"# {title}\n\n{body}"


def mark_sent_to_kindle(filepath: Path) -> None:
    """Update the sent-to-kindle property to yes in the article's frontmatter."""
    content = filepath.read_text(encoding="utf-8")
    updated = re.sub(
        r'^(sent-to-kindle:)\s*.*$',
        r'\1 yes',
        content,
        flags=re.MULTILINE
    )
    filepath.write_text(updated, encoding="utf-8")


def send_to_kindle(epub_path: Path, title: str) -> bool:
    """Send the epub to Kindle via calibre-smtp."""
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not password:
        print("Error: GMAIL_APP_PASSWORD environment variable not set.")
        return False

    cmd = [
        "calibre-smtp",
        "--attachment", str(epub_path),
        "--relay", "smtp.gmail.com",
        "--port", "587",
        "--encryption", "TLS",
        "--user", "vkatariya8@gmail.com",
        "--password", password,
        "vkatariya8@gmail.com",
        "vishal.katariya@kindle.com",
        title,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error sending to Kindle: {result.stderr}")
        return False
    return True


def create_metadata(articles: list[Path]) -> str:
    """Create YAML metadata for the epub."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Get date range from articles
    dates = [get_article_date(a) for a in articles]
    dates = [d for d in dates if d]

    if dates:
        oldest_date = min(dates)
        newest_date = max(dates)
        date_range = f"{oldest_date} to {newest_date}" if oldest_date != newest_date else oldest_date
    else:
        date_range = "various dates"

    return f"""---
title: "Articles Bundle - {today}"
subtitle: "Collection of {len(articles)} articles from {date_range}"
author: "Various Authors"
date: "{today}"
lang: en
---

"""


def main():
    # Parse optional command-line arguments
    parser = argparse.ArgumentParser(description="Bundle articles into epub for Kindle")
    parser.add_argument('--auto', action='store_true',
                        help='Automatically select oldest articles to reach target word count')
    args = parser.parse_args()

    # Step 1: Set fixed target word count
    TARGET_WORDS = 20000
    print(f"Target word count: {TARGET_WORDS:,} words\n")

    # Step 2: Get candidate articles (unsent only)
    candidates = get_candidate_articles(filter_sent=True)

    if not candidates:
        print("No unsent articles found in Inbox.")
        print("All articles have already been sent to Kindle.")
        return

    print(f"Found {len(candidates)} unsent article(s) available for selection.\n")

    # Step 3: Ask for mode if not specified via command line
    select_newest = False
    if args.auto:
        use_auto = True
    else:
        while True:
            response = input("Selection mode (a=automatic, i=interactive): ").strip().lower()
            if response in ['a', 'auto', 'automatic']:
                use_auto = True
                break
            elif response in ['i', 'interactive', 'manual', '']:
                use_auto = False
                break
            else:
                print("Please enter 'a' for automatic or 'i' for interactive.")

    # Step 4: Ask for oldest/newest when in automatic mode
    if use_auto:
        while True:
            response = input("Select (o=oldest articles first, n=newest articles first): ").strip().lower()
            if response in ['o', 'oldest', 'old', '']:
                select_newest = False
                break
            elif response in ['n', 'newest', 'new']:
                select_newest = True
                break
            else:
                print("Please enter 'o' for oldest or 'n' for newest.")

    # Step 5: Select articles (automatic or interactive)
    if use_auto:
        print()
        if select_newest:
            # Reverse candidates to get newest first
            candidates = list(reversed(candidates))
        articles = automatic_selection(candidates, TARGET_WORDS, select_newest)
    else:
        articles = display_article_selection_ui(candidates, TARGET_WORDS)

    # Step 4: Continue with existing epub creation logic
    today = datetime.now().strftime("%Y-%m-%d")
    output_file = OUTPUT_DIR / f"articles-{today}.epub"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Write metadata file
        metadata_file = tmpdir / "metadata.yaml"
        metadata_file.write_text(create_metadata(articles), encoding="utf-8")

        # Prepare each article with proper title heading
        prepared_files = []
        for i, article in enumerate(articles):
            prepared_content = prepare_article_for_epub(article)
            prepared_file = tmpdir / f"{i:02d}_{article.name}"
            prepared_file.write_text(prepared_content, encoding="utf-8")
            prepared_files.append(prepared_file)

        # Build pandoc command
        cmd = [
            "pandoc",
            str(metadata_file),
            *[str(f) for f in prepared_files],
            "-o", str(output_file),
            "--toc",
            "--toc-depth=1",
            "--epub-chapter-level=1",
            "--file-scope",
        ]

        print(f"\nCreating epub...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return

        print(f"Created: {output_file}")
        print(f"Size: {output_file.stat().st_size / 1024:.1f} KB")

    # Send to Kindle
    print("\nSending to Kindle...")
    book_title = f"Articles Bundle - {today}"
    if send_to_kindle(output_file, book_title):
        print("Sent successfully!")
    else:
        print("Failed to send to Kindle.")
        sys.exit(1)

    # Mark articles as sent to kindle
    print("\nMarking articles as sent-to-kindle...")
    for article in articles:
        mark_sent_to_kindle(article)
    print(f"Updated {len(articles)} article(s).")


if __name__ == "__main__":
    main()

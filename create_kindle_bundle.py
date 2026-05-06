#!/usr/bin/env python3
"""Interactively bundle articles from Inbox into an epub for Kindle."""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

import archive_read_articles
import count_images
import frontmatter_utils

INBOX_DIR = Path(__file__).parent / "Inbox"
OUTPUT_DIR = Path(__file__).parent
MAX_IMAGES = 10  # Articles with more images are excluded from bundling


def get_oldest_articles(count: int = 10) -> list[Path]:
    """Get the oldest N articles from Inbox, sorted by creation time."""
    articles = list(INBOX_DIR.glob("*.md"))
    articles.sort(key=lambda p: p.stat().st_ctime)
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
            key = key.strip().strip('"')
            value = value.strip().strip('"')
            if value:
                metadata[key] = value

    return metadata, body


def calculate_word_count(filepath: Path) -> int:
    """Calculate word count for article body (excluding frontmatter)."""
    content = filepath.read_text(encoding="utf-8")
    _, body = parse_frontmatter(content)
    return len(body.split())


def get_candidate_articles(filter_sent: bool = True) -> tuple[list[tuple[Path, dict]], int]:
    """Get candidate articles with metadata, sorted oldest first.

    Returns tuple of:
        - list of (filepath, metadata_dict) tuples
        - int count of articles skipped for having too many images
    metadata_dict contains: title, word_count, date, ctime
    """
    articles = list(INBOX_DIR.glob("*.md"))

    candidates = []
    skipped_for_images = 0
    for article in articles:
        content = article.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)

        # Filter out already-sent articles if requested
        if filter_sent and metadata.get('sent-to-kindle') == 'yes':
            continue

        # Get image count for display
        image_count = int(metadata.get('image_count', 0))

        # Skip articles with too many images
        if image_count > MAX_IMAGES:
            skipped_for_images += 1
            continue

        article_metadata = {
            'title': metadata.get('title', article.stem),
            'word_count': len(body.split()),
            'image_count': image_count,
            'date': metadata.get('created') or metadata.get('published') or
                    datetime.fromtimestamp(article.stat().st_mtime).strftime("%Y-%m-%d"),
            'ctime': article.stat().st_ctime
        }
        candidates.append((article, article_metadata))

    # Sort by creation date (oldest first) - uses 'created' from metadata
    candidates.sort(key=lambda x: x[1]['date'])
    return candidates, skipped_for_images


def count_total_images(articles: list[Path]) -> int:
    """Count total images across selected articles."""
    total = 0
    for article in articles:
        content = article.read_text(encoding="utf-8")
        metadata, _ = parse_frontmatter(content)
        total += int(metadata.get('image_count', 0))
    return total


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
    print(f"{'#':<4} {'Words':>8} {'Images':>7}  {'Date':<12}  {'Title':<45}")
    print("-" * 85)

    for idx, (filepath, meta) in enumerate(candidates, 1):
        title = meta['title'][:42] + "..." if len(meta['title']) > 45 else meta['title']
        print(f"{idx:<4} {meta['word_count']:>8,} {meta['image_count']:>7}  {meta['date']:<12}  {title}")

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


def automatic_selection(candidates: list[tuple[Path, dict]], target_words: int, select_newest: bool = False, count: int | None = None) -> list[Path]:
    """Automatically select articles until reaching target word count.

    Args:
        candidates: List of (filepath, metadata) tuples sorted by age
        target_words: Target total word count
        select_newest: If True, select newest articles; otherwise oldest
        count: If set, select exactly this many articles (ignores word count)

    Returns:
        List of selected article paths
    """
    selected = []
    total_words = 0
    
    # If count is specified, select exactly that many articles
    if count is not None:
        order = "newest" if select_newest else "oldest"
        print(f"Selecting {count} {order} articles...\n")
        
        for i, (filepath, meta) in enumerate(candidates):
            if i >= count:
                break
            selected.append(filepath)
            total_words += meta['word_count']
            print(f"  Added: {meta['title'][:60]} ({meta['word_count']:,} words)")
        
        print(f"\nSelected: {len(selected)} articles, {total_words:,} words")
        return selected

    # Original word-count-based selection
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
        r'"?sent-to-kindle"?:?\s*.*$',
        r'sent-to-kindle: yes',
        content,
        flags=re.MULTILINE
    )
    filepath.write_text(updated, encoding="utf-8")


def get_running_count() -> int:
    """Read the current running count from running_count.txt."""
    count_file = OUTPUT_DIR / "running_count.txt"
    if count_file.exists():
        try:
            return int(count_file.read_text(encoding="utf-8").strip())
        except (ValueError, IOError):
            pass
    return 0


def save_running_count(count: int) -> None:
    """Save the running count to running_count.txt."""
    count_file = OUTPUT_DIR / "running_count.txt"
    count_file.write_text(str(count), encoding="utf-8")


def get_cover_image(issue_number: int) -> Path | None:
    """Download a cover image from Lorem Picsum, seeded by issue number.

    Uses 960×600 (landscape-ish) which crops well to Kindle's thumbnail
    aspect ratio. The image is cached in .covers/ so repeated runs for
    the same issue number don't re-download.

    Returns Path to the cover image, or None on any failure (network
    error, HTTP error, etc.) so covers are always optional.
    """
    import urllib.request
    import urllib.error

    COVER_DIR = OUTPUT_DIR / ".covers"
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    cover_path = COVER_DIR / f"issue-{issue_number}.jpg"

    # Already cached — return immediately
    if cover_path.exists() and cover_path.stat().st_size > 0:
        return cover_path

    # Download from Lorem Picsum using issue number as seed for determinism
    url = f"https://picsum.photos/seed/kk{issue_number}/960/600"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kk-cli/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                print(f"  Cover image: HTTP {resp.status}, skipping.")
                return None
            cover_path.write_bytes(resp.read())
        print(f"  Cover image: downloaded (issue {issue_number})")
        return cover_path
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"  Cover image: unavailable ({e}), continuing without cover.")
        return None


def compress_and_convert_images(epub_path: Path) -> Path:
    """Compress and convert images in the EPUB for Kindle compatibility and size optimization.

    - Resizes all images to max 800px width / 600px height
    - Converts WebP/PNG to JPEG (Kindle doesn't support WebP; PNG transparency
      renders as black on eInk)
    - Compresses JPEGs for size
    - Updates the OPF manifest so Kindle can find the converted images
    """
    import zipfile
    import tempfile
    import xml.etree.ElementTree as ET

    temp_epub = epub_path.with_suffix('.tmp.epub')

    # First pass: count total images
    with zipfile.ZipFile(epub_path, 'r') as epub_zip:
        total_images = sum(1 for item in epub_zip.infolist()
                          if item.filename.lower().endswith(('.webp', '.jpg', '.jpeg', '.png', '.svg')))

    if total_images == 0:
        print("No images to compress.")
        return epub_path

    # First pass: compress and convert images with progress bar
    image_conversions = {}  # old filename -> new filename
    processed_count = 0

    with zipfile.ZipFile(epub_path, 'r') as epub_zip:
        with zipfile.ZipFile(temp_epub, 'w', zipfile.ZIP_DEFLATED) as new_zip:
            # Create progress bar for image processing
            with tqdm(total=total_images, desc="Compressing images", unit="img") as pbar:
                for item in epub_zip.infolist():
                    data = epub_zip.read(item.filename)

                    # Check if this is an image file
                    is_webp = item.filename.lower().endswith('.webp')
                    is_svg = item.filename.lower().endswith('.svg')
                    is_image = is_webp or is_svg or item.filename.lower().endswith(('.jpg', '.jpeg', '.png'))

                    if is_image:
                        processed_count += 1
                        pbar.set_postfix_str(f"Processing {Path(item.filename).name[:30]}")

                        # SVGs need special handling — convert to JPEG via sips
                        if is_svg:
                            tmp_suffix = '.svg'
                        elif is_webp:
                            tmp_suffix = '.webp'
                        else:
                            tmp_suffix = Path(item.filename).suffix

                        tmp_img = Path(tempfile.mktemp(suffix=tmp_suffix))
                        tmp_img.write_bytes(data)

                        jpg_path = None
                        try:
                            # Compress and convert using sips (macOS built-in)
                            # - Resample to max 800px width, 600px height
                            # - Convert to JPEG (handles WebP, PNG, SVG, etc.)
                            # - 50% quality — good balance for eInk
                            jpg_path = tmp_img.with_suffix('.jpg')
                            result = subprocess.run(
                                ['sips',
                                 '--resampleWidth', '800',
                                 '--resampleHeight', '600',
                                 '-s', 'format', 'jpeg',
                                 '-s', 'formatOptions', '50',
                                 str(tmp_img),
                                 '--out', str(jpg_path)],
                                capture_output=True
                            )

                            if result.returncode == 0 and jpg_path.exists():
                                new_filename = Path(item.filename).with_suffix('.jpg').name
                                # Preserve directory structure if any
                                if '/' in item.filename:
                                    new_filename = str(Path(item.filename).parent / new_filename)

                                original_size = len(data)
                                compressed_size = jpg_path.stat().st_size

                                # Always use the JPEG version for Kindle compatibility
                                # (even if larger — format compatibility matters more than size)
                                if compressed_size < original_size:
                                    compression_ratio = (1 - compressed_size/original_size) * 100
                                    status = "Converted" if (is_webp or is_svg) else "Compressed"
                                    pbar.set_postfix_str(f"{status}: {compression_ratio:.1f}% smaller")
                                else:
                                    pbar.set_postfix_str("Converted to JPEG for compatibility")

                                new_zip.writestr(new_filename, jpg_path.read_bytes())
                                image_conversions[item.filename] = new_filename
                            else:
                                # Compression failed, write original
                                new_zip.writestr(item, data)
                                pbar.set_postfix_str(f"Warning: Could not compress {Path(item.filename).name[:20]}")
                        finally:
                            if tmp_img.exists():
                                tmp_img.unlink()
                            if jpg_path and jpg_path.exists():
                                jpg_path.unlink()

                        pbar.update(1)
                    else:
                        new_zip.writestr(item, data)

    temp_epub.replace(epub_path)

    # Second pass: update HTML references AND the OPF manifest
    temp_epub2 = epub_path.with_suffix('.tmp2.epub')

    with zipfile.ZipFile(epub_path, 'r') as epub_zip:
        with zipfile.ZipFile(temp_epub2, 'w', zipfile.ZIP_DEFLATED) as new_zip:
            for item in epub_zip.infolist():
                data = epub_zip.read(item.filename)

                # Update HTML/XHTML files to reference new filenames
                if item.filename.endswith(('.html', '.xhtml')):
                    for old_name, new_name in image_conversions.items():
                        old_basename = Path(old_name).name
                        new_basename = Path(new_name).name
                        data = data.replace(old_basename.encode(), new_basename.encode())

                # Update OPF manifest (critical: Kindle won't find images otherwise)
                if item.filename.endswith('.opf'):
                    data = _update_opf_manifest(data, image_conversions)

                new_zip.writestr(item, data)

    temp_epub2.replace(epub_path)

    print(f"\nProcessed {processed_count} images for Kindle compatibility.")
    return epub_path


def _update_opf_manifest(opf_bytes: bytes, image_conversions: dict[str, str]) -> bytes:
    """Update the EPUB OPF manifest to reflect renamed/converted images.

    For each converted image, updates the <item> element's href and media-type
    so Kindle's reader can locate the image file.
    """
    import xml.etree.ElementTree as ET

    opf_str = opf_bytes.decode('utf-8')

    for old_name, new_name in image_conversions.items():
        old_basename = Path(old_name).name
        new_basename = Path(new_name).name
        old_ext = Path(old_name).suffix.lower()
        new_ext = Path(new_name).suffix.lower()

        # Build media-type mapping
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml',
        }
        old_media = media_types.get(old_ext, 'image/jpeg')
        new_media = media_types.get(new_ext, 'image/jpeg')

        # Update href attribute: old_basename → new_basename
        # Use a regex that targets href="...old_basename" in <item> elements
        opf_str = re.sub(
            r'(<item\b[^>]*?\bhref=")([^"]*' + re.escape(old_basename) + r')(")',
            lambda m: m.group(1) + m.group(2).replace(old_basename, new_basename) + m.group(3),
            opf_str
        )

        # Update media-type for the same item
        opf_str = re.sub(
            r'(<item\b[^>]*?\bhref="[^"]*' + re.escape(new_basename) + r'"[^>]*?\bmedia-type=")' + re.escape(old_media) + r'(")',
            r'\1' + new_media + r'\2',
            opf_str
        )

    return opf_str.encode('utf-8')


def send_to_kindle(epub_path: Path, title: str) -> bool:
    """Send the epub to Kindle via calibre-smtp with progress indication."""
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

    # Show spinner while sending email
    import threading
    stop_spinner = threading.Event()
    
    def spinner():
        spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        i = 0
        while not stop_spinner.is_set():
            print(f"\r{spinner_chars[i % len(spinner_chars)]} Uploading to Kindle...", end='', flush=True)
            i += 1
            time.sleep(0.1)
    
    spinner_thread = threading.Thread(target=spinner)
    spinner_thread.start()
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        stop_spinner.set()
        spinner_thread.join()
        print("\r" + " " * 50 + "\r", end='')  # Clear spinner line

    if result.returncode != 0:
        print(f"Error sending to Kindle: {result.stderr}")
        return False
    return True


def create_metadata(articles: list[Path], issue_number: int) -> str:
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
title: "Digest: Issue {issue_number}"
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
    parser.add_argument('--count', type=int, default=None,
                        help='Number of oldest articles to select')
    parser.add_argument('--oldest', action='store_true',
                        help='Select oldest articles first (for auto mode)')
    args = parser.parse_args()

    # Step 1: Update image counts
    print("Updating image counts...")
    stats = count_images.update_image_counts()
    print(f"Processed {stats['total']} article(s), updated {stats['updated']}\n")

    # Step 1.5: Normalize frontmatter
    print("Normalizing frontmatter...")
    frontmatter_utils.normalize_inbox_articles()

    print("\nStripping UTM parameters from sources...")
    utm_stats = frontmatter_utils.strip_utm_from_inbox_sources()
    print(f"  Cleaned {utm_stats['updated']} of {utm_stats['total']} article sources")

    print("\nCleaning question marks from filenames...")
    filename_stats = frontmatter_utils.clean_inbox_filenames()
    print(f"  Renamed {filename_stats['renamed']} files")

    # Step 1.75: Archive articles marked as read
    print("\nArchiving read articles...")
    archive_stats = archive_read_articles.archive_read_articles()
    if archive_stats['archived'] > 0 or archive_stats['dnf'] > 0:
        print(f"  Archived {archive_stats['archived']} article(s) marked as read and {archive_stats['dnf']} article(s) marked as DNF")
    print(f"  Kept {archive_stats['skipped']} unread article(s) in Inbox")

    # Step 2: Set fixed target word count
    TARGET_WORDS = 20000
    print(f"Target word count: {TARGET_WORDS:,} words\n")

    # Step 3: Get candidate articles (unsent only, filtered by image count)
    candidates, skipped_for_images = get_candidate_articles(filter_sent=True)

    if skipped_for_images > 0:
        print(f"By the way, I'm excluding {skipped_for_images} article(s) because they have too many images (>{MAX_IMAGES}).")
        print()

    if not candidates:
        print("No unsent articles found in Inbox.")
        print("All articles have already been sent to Kindle or have too many images.")
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
        if args.oldest or args.count:
            select_newest = False
        else:
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
        articles = automatic_selection(candidates, TARGET_WORDS, select_newest, args.count)
    else:
        articles = display_article_selection_ui(candidates, TARGET_WORDS)

    # Count total images before creating EPUB
    total_images = count_total_images(articles)
    print(f"\nFound {total_images} images across {len(articles)} articles")

    # Get next issue number from running count
    current_count = get_running_count()
    issue_number = current_count + 1
    print(f"Generating Digest: Issue {issue_number}")

    # Step 4: Continue with existing epub creation logic
    today = datetime.now().strftime("%Y-%m-%d")
    epub_file = OUTPUT_DIR / f"Digest-Issue-{issue_number}.epub"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Write metadata file
        metadata_file = tmpdir / "metadata.yaml"
        metadata_file.write_text(create_metadata(articles, issue_number), encoding="utf-8")

        # Prepare each article with proper title heading
        prepared_files = []
        for i, article in enumerate(tqdm(articles, desc="Preparing articles", unit="article")):
            prepared_content = prepare_article_for_epub(article)
            prepared_file = tmpdir / f"{i:02d}_{article.name}"
            prepared_file.write_text(prepared_content, encoding="utf-8")
            prepared_files.append(prepared_file)

        # Download cover image (seeded by issue number, cached in .covers/)
        cover_path = get_cover_image(issue_number)

        # Build pandoc command with Kindle-optimized CSS
        css_file = OUTPUT_DIR / "kindle.css"
        cmd = [
            "pandoc",
            str(metadata_file),
            *[str(f) for f in prepared_files],
            "-o", str(epub_file),
            "--to", "epub3",
            "--css", str(css_file),
            "--metadata", "lang=en-US",
            "--toc",
            "--toc-depth=1",
            "--epub-chapter-level=1",
            "--file-scope",
        ]

        # Attach cover image if we have one
        if cover_path:
            cmd.insert(1, str(cover_path))
            cmd.insert(1, "--epub-cover-image")

        print(f"\nCreating epub...")
        
        # Show two-phase spinner while pandoc runs
        # Phase 1: Downloading images (~70% of typical time)
        # Phase 2: Creating EPUB structure (~30% of typical time)
        import threading
        stop_spinner = threading.Event()
        start_time = time.time()
        
        def format_elapsed(seconds):
            """Format elapsed time as MM:SS."""
            mins, secs = divmod(int(seconds), 60)
            if mins > 0:
                return f"{mins}:{secs:02d}"
            return f"{secs}s"
        
        def spinner():
            spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            i = 0
            phase_switched = False
            
            while not stop_spinner.is_set():
                elapsed = time.time() - start_time
                elapsed_str = format_elapsed(elapsed)
                char = spinner_chars[i % len(spinner_chars)]
                
                # Switch phases after ~3 seconds (typical download time)
                # This is an estimate - pandoc doesn't give us real progress
                if not phase_switched and elapsed > 3:
                    phase_switched = True
                
                if not phase_switched:
                    msg = f"{char} Downloading {total_images} images... [{elapsed_str}]"
                else:
                    msg = f"{char} Creating EPUB structure... [{elapsed_str}]"
                
                print(f"\r{msg}", end='', flush=True)
                i += 1
                time.sleep(0.1)
        
        spinner_thread = threading.Thread(target=spinner)
        spinner_thread.start()
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        finally:
            stop_spinner.set()
            spinner_thread.join()
            elapsed_total = time.time() - start_time
            print("\r" + " " * 70 + "\r", end='')  # Clear spinner line

        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return

        # Format elapsed time
        mins, secs = divmod(int(elapsed_total), 60)
        if mins > 0:
            elapsed_fmt = f"{mins}m {secs}s"
        else:
            elapsed_fmt = f"{secs}s"
        
        print(f"✓ EPUB created in {elapsed_fmt} (processed ~{total_images} images)")
        print(f"  File: {epub_file}")
        print(f"  Size: {epub_file.stat().st_size / 1024:.1f} KB")

        # Compress and convert images for Kindle compatibility and size optimization
        compress_and_convert_images(epub_file)
        print(f"Size after compression: {epub_file.stat().st_size / 1024:.1f} KB")

    # Check file size against 25MB attachment limit
    SIZE_LIMIT_MB = 25
    SIZE_LIMIT = SIZE_LIMIT_MB * 1024 * 1024  # 25 MB in bytes
    file_size = epub_file.stat().st_size

    if file_size > SIZE_LIMIT:
        size_mb = file_size / (1024 * 1024)
        print(f"\nError: EPUB file is {size_mb:.1f}MB, which exceeds the {SIZE_LIMIT_MB}MB attachment limit.")
        print("Please make one of the following changes and re-run:")
        print("  - Remove some articles from the selection")
        print("  - Lower the target word count")
        print("  - Select articles with fewer images")
        sys.exit(1)

    # Send to Kindle
    print("\nSending to Kindle...")
    book_title = f"Digest: Issue {issue_number}"
    if send_to_kindle(epub_file, book_title):
        print("Sent successfully!")
        save_running_count(issue_number)

        # Mark articles as sent to kindle AFTER successful sending
        print("\nMarking articles as sent-to-kindle...")
        for article in tqdm(articles, desc="Updating articles", unit="article"):
            mark_sent_to_kindle(article)
        print(f"Updated {len(articles)} article(s).")
    else:
        print("Failed to send to Kindle.")
        sys.exit(1)


if __name__ == "__main__":
    main()

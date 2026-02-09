#!/usr/bin/env python3
"""CLI tool to process articles that have been sent to Kindle."""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

INBOX_DIR = Path(__file__).parent / "Inbox"
ARCHIVE_DIR = Path(__file__).parent / "Archive"


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    end_match = re.search(r'\n---\n', content[3:])
    if not end_match:
        return {}, content

    frontmatter_str = content[4:end_match.start() + 3]
    body = content[end_match.end() + 4:]

    # Simple YAML parsing for our specific format
    frontmatter = {}
    current_key = None
    current_list = None
    lines = frontmatter_str.split('\n')

    for i, line in enumerate(lines):
        if not line.strip():
            continue

        # Check if it's a list item
        if line.startswith('  - '):
            if current_list is not None:
                current_list.append(line[4:].strip().strip('"'))
            continue

        # Check for key: value
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip().strip('"')

            if value:
                frontmatter[key] = value
                current_key = None
                current_list = None
            else:
                # Check if next line is a list item
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if next_line.startswith('  - '):
                    frontmatter[key] = []
                    current_key = key
                    current_list = frontmatter[key]
                else:
                    # Empty value
                    frontmatter[key] = ""
                    current_key = None
                    current_list = None

    return frontmatter, body


def serialize_frontmatter(frontmatter: dict, body: str) -> str:
    """Serialize frontmatter dict back to markdown format."""
    lines = ["---"]

    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                if item.startswith("[[") or " " in item:
                    lines.append(f'  - "{item}"')
                else:
                    lines.append(f"  - {item}")
        elif value is None or value == "":
            lines.append(f"{key}:")
        else:
            # Quote if contains special chars
            if isinstance(value, str) and (":" in value or '"' in value):
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")

    lines.append("---")
    return "\n".join(lines) + "\n" + body


def get_kindle_articles() -> list[Path]:
    """Find all articles in Inbox with sent-to-kindle: yes."""
    articles = []

    for md_file in INBOX_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        frontmatter, _ = parse_frontmatter(content)

        if frontmatter.get("sent-to-kindle") == "yes":
            articles.append(md_file)

    return articles


def process_article(filepath: Path) -> None:
    """Process a single article through the interactive flow."""
    content = filepath.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)

    title = frontmatter.get("title", filepath.stem)
    author = frontmatter.get("author", "Unknown")
    if isinstance(author, list):
        author = ", ".join(a.strip("[]") for a in author)

    print("\n" + "=" * 60)
    print(f"Title: {title}")
    print(f"Author: {author}")
    print("=" * 60)

    # Step 1: Skip?
    skip = input("\n[1/4] Skip this article? (y to skip, Enter to continue): ").strip().lower()
    if skip == "y":
        print("Skipping...")
        return

    # Step 2: Like?
    like = input("[2/4] Like this article? (y/n, Enter for no): ").strip().lower()
    if like == "y":
        frontmatter["liked"] = "yes"
        print("Marked as liked.")

    # Step 3: Notes?
    notes_input = input("[3/4] Quick notes (or Enter to skip): ").strip()
    if notes_input:
        existing_notes = frontmatter.get("notes", "")
        if existing_notes:
            frontmatter["notes"] = f"{existing_notes} | {notes_input}"
        else:
            frontmatter["notes"] = notes_input
        print("Notes saved.")

    # Step 4: Archive?
    archive = input("[4/4] Archive this article? (y/n, Enter for no): ").strip().lower()
    if archive == "y":
        frontmatter["read-status"] = "read"
        frontmatter["date-read"] = datetime.now().strftime("%Y-%m-%d")

        # Write updated content
        new_content = serialize_frontmatter(frontmatter, body)

        # Move to archive
        dest = ARCHIVE_DIR / filepath.name
        if dest.exists():
            # Handle name collision
            base = filepath.stem
            ext = filepath.suffix
            counter = 1
            while dest.exists():
                dest = ARCHIVE_DIR / f"{base}_{counter}{ext}"
                counter += 1

        dest.write_text(new_content, encoding="utf-8")
        filepath.unlink()
        print(f"Archived to: {dest.name}")
    else:
        # Still save any changes (like, notes)
        new_content = serialize_frontmatter(frontmatter, body)
        filepath.write_text(new_content, encoding="utf-8")
        print("Changes saved (not archived).")


def main():
    """Main entry point."""
    print("Article Processor")
    print("-" * 40)

    articles = get_kindle_articles()

    if not articles:
        print("No articles found with 'sent-to-kindle: yes' in Inbox.")
        return

    print(f"Found {len(articles)} article(s) to process.\n")

    for i, article in enumerate(articles, 1):
        print(f"\n[Article {i}/{len(articles)}]")
        try:
            process_article(article)
        except KeyboardInterrupt:
            print("\n\nExiting...")
            return

    print("\n" + "=" * 60)
    print("All articles processed!")
    print("=" * 60)


if __name__ == "__main__":
    main()

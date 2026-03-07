#!/usr/bin/env python3
"""Frontmatter utilities for normalizing YAML frontmatter in markdown files."""

import re
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


def serialize_frontmatter(frontmatter: dict, body: str) -> str:
    """Serialize frontmatter dict back to markdown format without quotes on keys."""
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
            if isinstance(value, str) and (":" in value or '"' in value):
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")

    lines.append("---")
    return "\n".join(lines) + "\n" + body


def normalize_file(filepath: Path) -> bool:
    """Normalize a single file's frontmatter (strip quotes from keys). Returns True if changed."""
    content = filepath.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)
    new_content = serialize_frontmatter(frontmatter, body)
    
    if new_content != content:
        filepath.write_text(new_content, encoding="utf-8")
        return True
    return False


def normalize_inbox_articles() -> dict:
    """Normalize frontmatter in all Inbox articles."""
    return _normalize_articles_in_dir(INBOX_DIR)


def normalize_archive_articles() -> dict:
    """Normalize frontmatter in all Archive articles."""
    return _normalize_articles_in_dir(ARCHIVE_DIR)


def _normalize_articles_in_dir(directory: Path) -> dict:
    """Normalize frontmatter in all markdown files in the given directory."""
    stats = {"updated": 0, "unchanged": 0, "total": 0}
    
    if not directory.exists():
        return stats
        
    for md_file in directory.glob("*.md"):
        stats["total"] += 1
        if normalize_file(md_file):
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1
    
    return stats


def main():
    """Main entry point for standalone usage."""
    print("Normalizing frontmatter in Inbox articles...")
    inbox_stats = normalize_inbox_articles()
    
    print(f"Inbox: {inbox_stats['total']} processed, {inbox_stats['updated']} updated, {inbox_stats['unchanged']} unchanged")
    
    print("\nNormalizing frontmatter in Archive articles...")
    archive_stats = normalize_archive_articles()
    
    print(f"Archive: {archive_stats['total']} processed, {archive_stats['updated']} updated, {archive_stats['unchanged']} unchanged")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Frontmatter utilities for normalizing YAML frontmatter in markdown files."""

import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

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
    body = content[end_match.end() + 3:]

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


def strip_utm_from_source_url(url: str) -> str:
    """Strip UTM parameters from a URL."""
    if not url or not url.startswith('http'):
        return url
    
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    
    # Remove UTM parameters
    utm_params = {k: v for k, v in query_params.items() if not k.startswith('utm_')}
    
    if utm_params == query_params:
        # No UTM params to remove
        return url
    
    # Rebuild URL without UTM params
    new_query = urlencode(utm_params, doseq=True)
    cleaned_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))
    
    return cleaned_url


def strip_utm_from_inbox_sources() -> dict:
    """Strip UTM parameters from source URLs in Inbox articles."""
    stats = {"total": 0, "updated": 0, "unchanged": 0}
    
    if not INBOX_DIR.exists():
        return stats
    
    for md_file in INBOX_DIR.glob("*.md"):
        stats["total"] += 1
        content = md_file.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(content)
        
        source = frontmatter.get("source", "")
        if source:
            cleaned_source = strip_utm_from_source_url(source)
            if cleaned_source != source:
                frontmatter["source"] = cleaned_source
                new_content = serialize_frontmatter(frontmatter, body)
                md_file.write_text(new_content, encoding="utf-8")
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
        else:
            stats["unchanged"] += 1
    
    return stats


def clean_inbox_filenames() -> dict:
    """Remove question marks from filenames in Inbox."""
    stats = {"total": 0, "renamed": 0}
    
    if not INBOX_DIR.exists():
        return stats
    
    for md_file in INBOX_DIR.glob("*.md"):
        stats["total"] += 1
        
        if "?" in md_file.name:
            # Create new filename without question marks
            new_name = md_file.name.replace("?", "")
            new_path = INBOX_DIR / new_name
            
            # Handle name collision
            if new_path.exists():
                base = new_path.stem
                ext = new_path.suffix
                counter = 1
                while new_path.exists():
                    new_path = INBOX_DIR / f"{base}_{counter}{ext}"
                    counter += 1
            
            # Rename the file
            md_file.rename(new_path)
            stats["renamed"] += 1
    
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

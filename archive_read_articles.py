#!/usr/bin/env python3
"""Archive articles from Inbox that have been marked as read."""

import re
from datetime import datetime
from pathlib import Path

INBOX_DIR = Path(__file__).parent / "Inbox"
ARCHIVE_DIR = Path(__file__).parent / "Archive"
DNF_DIR = Path(__file__).parent / "DNF"


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
            if isinstance(value, str) and (":" in value or '"' in value):
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")

    lines.append("---")
    return "\n".join(lines) + "\n" + body


def get_read_status(content: str) -> str | None:
    """Extract the read-status value from frontmatter, handling various formats."""
    frontmatter, _ = parse_frontmatter(content)
    
    for key in ('read-status', 'read_status'):
        if key in frontmatter:
            return frontmatter[key] if frontmatter[key] else None
    
    return None


def archive_read_articles() -> dict:
    """Move articles marked as read or DNF from Inbox to their respective folders.

    Returns stats dict with keys:
        - archived: number of articles moved to Archive
        - dnf: number of articles moved to DNF
        - skipped: number of articles not marked as read or dnf
    """
    stats = {"archived": 0, "dnf": 0, "skipped": 0}

    ARCHIVE_DIR.mkdir(exist_ok=True)
    DNF_DIR.mkdir(exist_ok=True)

    for md_file in INBOX_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        read_status = get_read_status(content)

        if read_status in ("read", "yes"):
            # Parse, set date-read, and write to Archive
            frontmatter, body = parse_frontmatter(content)
            frontmatter["date-read"] = datetime.now().strftime("%Y-%m-%d")
            updated_content = serialize_frontmatter(frontmatter, body)

            # Handle name collisions
            dest = ARCHIVE_DIR / md_file.name
            if dest.exists():
                base = md_file.stem
                ext = md_file.suffix
                counter = 1
                while dest.exists():
                    dest = ARCHIVE_DIR / f"{base}_{counter}{ext}"
                    counter += 1

            dest.write_text(updated_content, encoding="utf-8")
            md_file.unlink()
            stats["archived"] += 1
        elif read_status == "dnf":
            # Parse, set date-read, and write to DNF
            frontmatter, body = parse_frontmatter(content)
            frontmatter["date-read"] = datetime.now().strftime("%Y-%m-%d")
            updated_content = serialize_frontmatter(frontmatter, body)

            # Handle name collisions
            dest = DNF_DIR / md_file.name
            if dest.exists():
                base = md_file.stem
                ext = md_file.suffix
                counter = 1
                while dest.exists():
                    dest = DNF_DIR / f"{base}_{counter}{ext}"
                    counter += 1

            dest.write_text(updated_content, encoding="utf-8")
            md_file.unlink()
            stats["dnf"] += 1
        else:
            stats["skipped"] += 1

    return stats


def main():
    """Main entry point."""
    print("Checking for read articles to archive...")
    stats = archive_read_articles()

    if stats["archived"] > 0 or stats["dnf"] > 0:
        print(f"  Archived {stats['archived']} article(s) marked as read and {stats['dnf']} article(s) marked as DNF")
    print(f"  Kept {stats['skipped']} unread article(s) in Inbox")


if __name__ == "__main__":
    main()

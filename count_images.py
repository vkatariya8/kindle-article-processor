#!/usr/bin/env python3
"""Count images in markdown files and update frontmatter with image_count."""

import re
from pathlib import Path

INBOX_DIR = Path(__file__).parent / "Inbox"


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
            key = key.strip()
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


def count_images(body: str) -> int:
    """Count images in markdown body using ![alt](url) pattern."""
    image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    matches = re.findall(image_pattern, body)
    return len(matches)


def update_image_counts() -> dict:
    """Update all markdown files in Inbox with image_count in frontmatter."""
    stats = {"updated": 0, "unchanged": 0, "total": 0}

    for md_file in INBOX_DIR.glob("*.md"):
        stats["total"] += 1
        content = md_file.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(content)

        image_count = count_images(body)
        existing_count = frontmatter.get("image_count")

        if existing_count is None or str(existing_count) != str(image_count):
            frontmatter["image_count"] = str(image_count)
            new_content = serialize_frontmatter(frontmatter, body)
            md_file.write_text(new_content, encoding="utf-8")
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1

    return stats


def main():
    """Main entry point."""
    print("Counting images in Inbox articles...")
    stats = update_image_counts()

    print(f"Processed {stats['total']} article(s)")
    print(f"  Updated: {stats['updated']}")
    print(f"  Unchanged: {stats['unchanged']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate a witty weekly digest of reading activity."""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

INBOX_DIR = Path(__file__).parent / "Inbox"
ARCHIVE_DIR = Path(__file__).parent / "Archive"
DNF_DIR = Path(__file__).parent / "DNF"
OUTPUT_DIR = Path(__file__).parent / "Weekly-Digests"
STATS_FILE = Path(__file__).parent / "weekly_stats.json"
OLLAMA_MODEL = "qwen3:4b-instruct"
OLLAMA_URL = "http://localhost:11434/api/generate"


def get_week_boundaries(reference_date: datetime | None = None) -> tuple[datetime, datetime]:
    """Return (week_start, week_end) where week_start is the most recent Sunday
    and week_end is the reference date (or Saturday if reference_date is None)."""
    if reference_date is None:
        reference_date = datetime.now()
    
    # Find the most recent Sunday (weekday 6)
    days_since_sunday = (reference_date.weekday() + 1) % 7
    week_start = reference_date - timedelta(days=days_since_sunday)
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    week_end = reference_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return week_start, week_end


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
        
        # Extract authors
        author = frontmatter.get("author", "")
        if isinstance(author, list):
            author = ", ".join(str(a) for a in author)
        
        articles.append({
            "title": frontmatter.get("title", md_file.stem),
            "source": frontmatter.get("source", ""),
            "author": author,
            "description": frontmatter.get("description", ""),
            "tags": tags,
            "created": parse_date(frontmatter.get("created")),
            "date_read": parse_date(frontmatter.get("date-read")),
            "read_status": frontmatter.get("read-status", ""),
            "liked": frontmatter.get("liked", ""),
            "kats_kable": frontmatter.get("kats-kable", ""),
            "file": str(md_file.name),
            "directory": directory.name,
        })
    return articles


def compute_weekly_stats(articles: list[dict], week_start: datetime, week_end: datetime) -> dict:
    """Compute weekly statistics from article data."""
    new_articles = []
    read_articles = []
    dnf_articles = []
    liked_articles = []
    kats_kable_articles = []
    
    for article in articles:
        # New articles: created this week
        if article["created"] and week_start <= article["created"] <= week_end:
            new_articles.append(article)
        
        # Read articles: date-read this week and finished
        if article["date_read"] and week_start <= article["date_read"] <= week_end:
            if article["read_status"] == "dnf":
                dnf_articles.append(article)
            else:
                read_articles.append(article)
            
            # Liked articles: read this week AND liked
            if article["liked"] in ("yes", "true", "1"):
                liked_articles.append(article)
            
            # Kat's Kable articles: read this week AND has kats-kable set
            if article["kats_kable"] and article["kats_kable"] not in ("", "0", "no", "false"):
                kats_kable_articles.append(article)
    
    # Inbox backlog: unread articles in Inbox
    inbox_unread = [a for a in articles if a["directory"] == "Inbox" and a["read_status"] not in ("read", "yes")]
    
    # Archive total
    archive_total = len([a for a in articles if a["directory"] == "Archive"])
    
    # DNF total
    dnf_total = len([a for a in articles if a["directory"] == "DNF"])
    
    # Top sources among read articles
    sources = {}
    for article in read_articles:
        source = article["source"]
        if source:
            # Extract domain
            domain = re.sub(r'^https?://', '', source)
            domain = domain.split('/')[0]
            sources[domain] = sources.get(domain, 0) + 1
    top_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Top tags among read/liked articles
    tags = {}
    for article in read_articles + liked_articles:
        for tag in article["tags"]:
            if tag and tag != "clippings":
                tags[tag] = tags.get(tag, 0) + 1
    top_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        "new_articles": new_articles,
        "read_articles": read_articles,
        "dnf_articles": dnf_articles,
        "liked_articles": liked_articles,
        "kats_kable_articles": kats_kable_articles,
        "stats": {
            "new_count": len(new_articles),
            "read_count": len(read_articles),
            "dnf_count": len(dnf_articles),
            "liked_count": len(liked_articles),
            "kats_kable_count": len(kats_kable_articles),
            "inbox_unread_count": len(inbox_unread),
            "archive_total": archive_total,
            "dnf_total": dnf_total,
        },
        "top_sources": top_sources,
        "top_tags": top_tags,
    }


def load_previous_stats() -> dict | None:
    """Load previous week's stats for comparison."""
    if not STATS_FILE.exists():
        return None
    
    try:
        with open(STATS_FILE, "r") as f:
            data = json.load(f)
        
        # Get the most recent week
        weeks = sorted(data.keys())
        if weeks:
            return data[weeks[-1]]
    except (json.JSONDecodeError, IOError):
        pass
    
    return None


def save_weekly_stats(week_key: str, stats: dict) -> None:
    """Save weekly stats to JSON file."""
    data = {}
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    data[week_key] = {
        "new_count": stats["stats"]["new_count"],
        "read_count": stats["stats"]["read_count"],
        "dnf_count": stats["stats"]["dnf_count"],
        "liked_count": stats["stats"]["liked_count"],
        "kats_kable_count": stats["stats"]["kats_kable_count"],
        "inbox_unread_count": stats["stats"]["inbox_unread_count"],
        "archive_total": stats["stats"]["archive_total"],
        "dnf_total": stats["stats"]["dnf_total"],
        "week_start": stats["week_start"],
        "week_end": stats["week_end"],
    }
    
    with open(STATS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def build_ollama_prompt(stats: dict, week_start: datetime, week_end: datetime, prev_stats: dict | None) -> str:
    """Build the prompt for ollama."""
    
    def article_summary(article: dict) -> dict:
        return {
            "title": article["title"],
            "source": article["source"][:100] if article["source"] else "",
            "author": article["author"][:100] if article["author"] else "",
            "description": article["description"][:200] if article["description"] else "",
            "tags": article["tags"][:5] if article["tags"] else [],
        }
    
    new_summaries = [article_summary(a) for a in stats["new_articles"]]
    read_summaries = [article_summary(a) for a in stats["read_articles"]]
    dnf_summaries = [article_summary(a) for a in stats["dnf_articles"]]
    liked_summaries = [article_summary(a) for a in stats["liked_articles"]]
    kats_kable_summaries = [article_summary(a) for a in stats["kats_kable_articles"]]
    
    # Build comparison text
    comparison = {}
    if prev_stats:
        comparison = {
            "new_delta": stats["stats"]["new_count"] - prev_stats.get("new_count", 0),
            "read_delta": stats["stats"]["read_count"] - prev_stats.get("read_count", 0),
            "dnf_delta": stats["stats"]["dnf_count"] - prev_stats.get("dnf_count", 0),
            "liked_delta": stats["stats"]["liked_count"] - prev_stats.get("liked_count", 0),
            "kats_kable_delta": stats["stats"]["kats_kable_count"] - prev_stats.get("kats_kable_count", 0),
        }
    
    context = {
        "week_range": f"{week_start.strftime('%B %d')} – {week_end.strftime('%B %d, %Y')}",
        "stats": stats["stats"],
        "comparison": comparison,
        "top_sources": stats["top_sources"],
        "top_tags": stats["top_tags"],
        "new_articles": new_summaries,
        "read_articles": read_summaries,
        "dnf_articles": dnf_summaries,
        "liked_articles": liked_summaries,
        "kats_kable_articles": kats_kable_summaries,
    }
    
    prompt = f"""You are a witty, slightly sarcastic curator writing a weekly reading digest called "The Weekly Kable." Write in a fun, conversational tone — like a smart friend catching up over coffee.

Here is this week's reading data (JSON):

{json.dumps(context, indent=2)}

Write a newsletter-style recap with these sections:

1. **Headline**: A punchy, fun headline for the week.
2. **Opening Banter**: 2-3 sentences setting the tone. Mention the week range.
3. **Stats Corner**: A compact bullet list of the week's numbers. Include week-over-week changes if available (e.g., "+3 from last week" or "-2 from last week"). If no previous week data, just show the raw numbers.
4. **New Arrivals**: Briefly mention 2-3 interesting new articles that arrived this week. One sentence each.
5. **Reading Room**: Highlight 2-3 articles that were read this week. What made them interesting? Draw connections between them if possible.
6. **DNF Corner**: If any articles were marked DNF (did not finish), mention them with a brief, lighthearted note.
7. **Kable Korner**: Mention any articles that made it to Kat's Kable this week. Be enthusiastic.
8. **What We Learned**: 2-3 sentences synthesizing themes or surprising connections across the week's reading.
9. **Closing**: A witty sign-off.

Keep the whole thing under 600 words. Use markdown formatting. Make it genuinely fun to read — not just a dry report."""
    
    return prompt


def call_ollama(prompt: str) -> str:
    """Call ollama API and return the generated text."""
    try:
        import urllib.request
        import urllib.error
        
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        }).encode("utf-8")
        
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("response", "")
    
    except urllib.error.URLError as e:
        print(f"Error connecting to ollama: {e}")
        print("Make sure ollama is running (ollama serve)")
        sys.exit(1)
    except Exception as e:
        print(f"Error calling ollama: {e}")
        sys.exit(1)


def save_digest(markdown_content: str, week_start: datetime, week_end: datetime) -> Path:
    """Save the digest as a markdown file."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    week_key = week_start.strftime("%Y-W%W")
    filename = f"{week_key}-Digest.md"
    filepath = OUTPUT_DIR / filename
    
    filepath.write_text(markdown_content, encoding="utf-8")
    return filepath


def print_summary(stats: dict, filepath: Path, week_start: datetime, week_end: datetime) -> None:
    """Print a compact summary to the terminal."""
    week_key = week_start.strftime("%Y-W%W")
    s = stats["stats"]
    
    print(f"\n📬 Weekly Digest: {week_start.strftime('%B %d')} – {week_end.strftime('%B %d, %Y')} ({week_key})")
    print(f"   📥 New: {s['new_count']} | ✅ Read: {s['read_count']} | 🚫 DNF: {s['dnf_count']} | ❤️  Liked: {s['liked_count']} | 📰 Kable: {s['kats_kable_count']}")
    print(f"   📂 Inbox backlog: {s['inbox_unread_count']} articles waiting | 🗄️  Archive: {s['archive_total']} total | 🗑️  DNF: {s['dnf_total']} total")
    print(f"   📝 Full digest saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Generate a witty weekly reading digest")
    parser.add_argument("--dry-run", action="store_true", help="Show stats without calling ollama")
    args = parser.parse_args()
    
    # Determine week boundaries
    week_start, week_end = get_week_boundaries()
    week_key = week_start.strftime("%Y-W%W")
    
    print(f"Generating digest for week {week_key} ({week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')})...")
    
    # Collect all articles
    print("\nScanning articles...")
    inbox_articles = collect_article_data(INBOX_DIR)
    archive_articles = collect_article_data(ARCHIVE_DIR)
    dnf_articles = collect_article_data(DNF_DIR)
    all_articles = inbox_articles + archive_articles + dnf_articles
    
    print(f"  Inbox: {len(inbox_articles)} articles")
    print(f"  Archive: {len(archive_articles)} articles")
    print(f"  DNF: {len(dnf_articles)} articles")
    
    # Compute stats
    print("\nComputing weekly stats...")
    stats = compute_weekly_stats(all_articles, week_start, week_end)
    stats["week_start"] = week_start.strftime("%Y-%m-%d")
    stats["week_end"] = week_end.strftime("%Y-%m-%d")
    
    s = stats["stats"]
    print(f"  New articles: {s['new_count']}")
    print(f"  Read articles: {s['read_count']}")
    print(f"  DNF articles: {s['dnf_count']}")
    print(f"  Liked articles: {s['liked_count']}")
    print(f"  Kat's Kable articles: {s['kats_kable_count']}")
    print(f"  Inbox backlog: {s['inbox_unread_count']}")
    
    # Load previous stats for comparison
    prev_stats = load_previous_stats()
    if prev_stats:
        print(f"\n  Comparison to last week:")
        deltas = {
            "New": s['new_count'] - prev_stats.get('new_count', 0),
            "Read": s['read_count'] - prev_stats.get('read_count', 0),
            "DNF": s['dnf_count'] - prev_stats.get('dnf_count', 0),
            "Liked": s['liked_count'] - prev_stats.get('liked_count', 0),
            "Kable": s['kats_kable_count'] - prev_stats.get('kats_kable_count', 0),
        }
        for label, delta in deltas.items():
            sign = "+" if delta > 0 else ""
            print(f"    {label}: {sign}{delta}")
    
    if args.dry_run:
        print("\n🛑 Dry run — skipping ollama call and file save.")
        return
    
    # Build prompt and call ollama
    print("\nSummoning the wit of qwen3:4b-instruct...")
    prompt = build_ollama_prompt(stats, week_start, week_end, prev_stats)
    digest_content = call_ollama(prompt)
    
    # Save digest
    filepath = save_digest(digest_content, week_start, week_end)
    
    # Save stats
    save_weekly_stats(week_key, stats)
    
    # Print summary
    print_summary(stats, filepath, week_start, week_end)


if __name__ == "__main__":
    main()

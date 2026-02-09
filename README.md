# Kindle Article Processor

CLI tools to bundle articles into Kindle-friendly epubs and process them after reading.

## Overview

This repository contains two Python scripts that manage your article reading workflow:

1. **`create_kindle_bundle.py`** - Selects articles from your Inbox, bundles them into an epub, and sends to your Kindle
2. **`process_articles.py`** - Processes articles you've read on Kindle, allowing you to add likes/notes and archive them

## Workflow

```
Inbox Folder → Create Bundle → Send to Kindle → Read → Process → Archive Folder
```

## Installation

```bash
# Clone the repository
git clone https://github.com/vkatariya8/kindle-article-processor.git
cd kindle-article-processor

# Install dependencies
pip install -r requirements.txt  # if needed
```

## Requirements

- Python 3.8+
- [Pandoc](https://pandoc.org/installing.html) - for epub generation
- [Calibre](https://calibre-ebook.com/download) - for `calibre-smtp` command
- Gmail account with App Password configured
- Environment variable: `GMAIL_APP_PASSWORD`

## Setup

1. **Create folder structure:**
   ```
   mkdir Inbox Archive
   ```

2. **Configure Gmail:**
   ```bash
   export GMAIL_APP_PASSWORD="your-app-password"
   ```

3. **Add your Kindle email:**
   Edit `create_kindle_bundle.py` and update the send_to_kindle() function with your Kindle email address.

## Usage

### Step 1: Add Articles to Inbox

Place markdown files with YAML frontmatter in the `Inbox/` folder:

```yaml
---
title: "Article Title"
author: "Author Name"
created: "2024-01-15"
sent-to-kindle: no
---

Article content here...
```

### Step 2: Create and Send Bundle

```bash
python create_kindle_bundle.py
```

This will:
- Show available articles (filtered to unsent)
- Let you select articles (interactive or automatic mode)
- Create an epub file
- Send it to your Kindle
- Mark articles as `sent-to-kindle: yes`

**Options:**
- `--auto` - Automatically select articles to reach target word count
- Interactive mode - Manually select articles by number

### Step 3: Process Read Articles

After reading on your Kindle:

```bash
python process_articles.py
```

This processes articles marked `sent-to-kindle: yes` and will:
1. Ask if you want to skip the article
2. Ask if you liked it (adds `liked: yes`)
3. Ask for quick notes (appends to `notes` field)
4. Ask to archive (moves to `Archive/` folder with `read-status: read` and `date-read: YYYY-MM-DD`)

## File Structure

```
.
├── Inbox/                    # Articles waiting to be sent
│   └── article.md           # Markdown files with YAML frontmatter
├── Archive/                  # Processed/read articles
│   └── article.md           # Moved here after processing
├── create_kindle_bundle.py  # Bundle creation script
├── process_articles.py      # Post-reading processing script
└── articles-YYYY-MM-DD.epub # Generated epub files
```

## Frontmatter Fields

Articles support the following YAML frontmatter:

- `title` - Article title
- `author` - Author name(s)
- `created` - Original creation date
- `published` - Publication date
- `sent-to-kindle` - Whether sent to Kindle (yes/no)
- `read-status` - Reading status (read/unread)
- `date-read` - Date marked as read (YYYY-MM-DD)
- `liked` - Whether you liked it (yes/no)
- `notes` - Your notes about the article

## Example Workflow

```bash
# 1. Add articles to Inbox/
cp ~/Downloads/article.md Inbox/

# 2. Create and send bundle to Kindle
python create_kindle_bundle.py

# 3. Read on your Kindle

# 4. Process after reading
python process_articles.py

# 5. Article is now in Archive/ with read status and date
```

## Tips

- Articles are sorted by age (oldest first) to ensure you read them in order
- Target word count is set to ~20,000 words per bundle (adjustable in code)
- The epub includes a table of contents
- Archived articles retain all metadata including your notes and likes

## License

MIT

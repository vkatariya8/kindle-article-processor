# AGENTS.md — Kindle Article Processor

Personal Python CLI for bundling markdown articles into Kindle epubs and tracking reading stats.

## Architecture

- **No packaging**: Plain Python scripts in repo root that import each other as modules. No `requirements.txt`, `setup.py`, or tests.
- **Entrypoints**:
  - `create_kindle_bundle.py` — bundles `Inbox/*.md` into epub, emails to Kindle
  - `process_articles.py` — interactive post-read workflow (like, notes, archive)
  - `weekly_digest.py` — generates reading digest via local Ollama
  - `archive_read_articles.py`, `frontmatter_utils.py`, `count_images.py` — shared utilities
  - `backfill_stats.py` — backfills `weekly_stats.json` from a historical vault path

## External Dependencies

These are **not** pip-installable and must be present on the system:

- **Pandoc** — epub generation (`pandoc` on PATH)
- **Calibre** — `calibre-smtp` command for emailing epubs
- **sips** — macOS built-in tool for image compression/conversion (grayscale JPEG, 600×800 max). The bundler will fail on non-macOS systems.
- **Ollama** — `weekly_digest.py` calls `http://localhost:11434/api/generate` with model `qwen3:4b-instruct`

Python dependency: `tqdm` (used for progress bars in bundler).

## Environment & Hardcoded Values

- `GMAIL_APP_PASSWORD` env var required for `calibre-smtp`
- Sender / Kindle emails are hardcoded in `create_kindle_bundle.py` (`vkatariya8@gmail.com`, `vishal.katariya@kindle.com`)

## Data Model

Articles are markdown files with YAML frontmatter. Key fields agents may edit:

| Field | Purpose |
|-------|---------|
| `title` | Article title |
| `author` | Author name(s); can be a list |
| `created` / `published` | Date strings (`YYYY-MM-DD`) |
| `sent-to-kindle` | `yes` / `no` — controls bundling eligibility |
| `read-status` | `read` triggers auto-archive to `Archive/` |
| `date-read` | Auto-set on archive (`YYYY-MM-DD`) |
| `liked` | `yes` / `no` |
| `notes` | Free-text; appended with `|` if multiple entries |
| `source` | URL; UTM params are auto-stripped by `frontmatter_utils` |
| `tags` | List of strings |
| `description` | Used by weekly digest |
| `kats-kable` | Truthy if article is curated for Kat's Kable newsletter |
| `image_count` | Auto-computed by `count_images.py` |

## Workflow Constraints

- **Image limit**: Articles with `image_count > 10` are excluded from bundling.
- **Size limit**: Generated epub must be ≤ 25 MB or the script exits with an error.
- **Heading demotion**: All headings in article bodies are shifted down one level (`h1 → h2`, etc.) during epub creation to avoid chapter conflicts.
- **Issue numbering**: Tracked in `running_count.txt` (plain integer). Each successful bundle increments it.
- **Auto-cleanup on bundle**: Before selection, the bundler normalizes frontmatter, strips UTM params, cleans `?` from filenames, and archives any already-read articles.

## File Layout

```
Inbox/          # Markdown articles awaiting bundling (gitignored)
Archive/        # Processed articles (gitignored)
kats_kable/     # Curated lists using Obsidian-style [[links]]
weekly_stats.json
running_count.txt
*.epub          # Generated bundles (gitignored)
```

## Running Scripts

```bash
# Bundle and send
python create_kindle_bundle.py        # interactive selection
python create_kindle_bundle.py --auto --count 5
python create_kindle_bundle.py --auto --newest

# Process after reading (interactive)
python process_articles.py

# Generate weekly digest (requires Ollama running)
python weekly_digest.py               # calls Ollama, saves to Weekly-Digests/
python weekly_digest.py --dry-run     # stats only, no LLM call

# Utilities (also run automatically by entrypoints)
python count_images.py
python frontmatter_utils.py
python archive_read_articles.py
```

## Style Notes

- Frontmatter keys are **not** quoted (e.g., `title: Foo`, not `"title": Foo`).
- String values containing `:` or `"` are quoted; list items containing spaces or `[[` are quoted.
- Use `read-status` (hyphen), not `read_status` (underscore). The parser accepts both but normalizes to hyphen.

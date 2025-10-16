# Public-Housing

## LH Announcement Crawler

A Python crawler that iterates over the "공고중" 모집공고 list on LH 청약플러스 and downloads every PDF attachment for offline analysis.

### Quick Start

1. Install dependencies:
    ```bash
    poetry add beautifulsoup4 requests responses pytest
    ```
2. Activate Poetry virtual environment
    ```bash
    poetry shell
    ```
3. Run the crawler (downloads PDFs to `assets/lh/pdfs` by default):
    ```bash
    python -m src.crawlers.lh_announcements --metadata assets/lh/metadata.json
    ```

Additional options:

-   `--output PATH` to override the download directory.
-   `--delay SECONDS` to throttle between page requests.
-   `--max-pages N` to limit pagination during testing.

See `docs/lh_crawler_design.md` for architecture notes.

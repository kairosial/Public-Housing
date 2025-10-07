# LH Announcement PDF Crawler Design

## Objective
Fetch every currently open LH rental housing announcement and download its accompanying PDF attachments. The crawler must traverse all paginated result pages exposed at `https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026` and persist PDFs locally for downstream analysis in the personalization service.

## High-Level Flow
1. Enumerate the paginated announcement list.
2. For each row, resolve the detail page URL and metadata (title, location, reception window, etc.).
3. Parse the detail view for document attachments (`.pdf`) and download each one to the configured destination.
4. Record crawler output (metadata + file paths) for future processing or notifications.

## Components
- **`LHAnnouncementCrawler`** (in `src/crawlers/lh_announcements.py`)
  - Manages HTTP session, pagination, attachment retrieval, and output persistence.
  - Exposes `crawl()` for batch operation and `iter_announcements()` generator for integration tests or pipelines.
- **`Announcement` dataclass**
  - Captures identifier, title, location, reception period, detail URL, and list of attachments.
- **`Attachment` dataclass**
  - Stores attachment name, URL, and resolved local file path.
- **CLI Entrypoint**
  - `python -m src.crawlers.lh_announcements --output assets/lh/pdfs` to run the crawler manually.

## Pagination Strategy
- Start at page 1 and repeatedly fetch list pages.
- Detect additional pages via paginator controls (look for anchors with `data-page`, `href` fragments, or `onclick` handlers). Stop when no new announcements are discovered or when paginator marks the current page as last.
- Add a short configurable throttle (`--delay`) to avoid overwhelming the remote service.

## Detail & Attachment Retrieval
- Resolve each announcement's detail link. LH currently renders detail URLs via inline scripts (e.g., `javascript:fn_view('BBSMSTR_ID','ANN_ID')`). Regex the parameters and submit the corresponding request.
- Detail pages contain an attachment table (`ul.board_attach` or similar). Filter `<a>` elements whose `href` ends with `.pdf` (case-insensitive).
- Use `urljoin` to derive fully qualified URLs before downloading.

## Download Management
- Persist PDFs under the configured output directory (default `assets/lh/pdfs`).
- Organise files per announcement using a slugified directory name to keep related documents together.
- Skip downloads when the exact file already exists unless `--force` is supplied.
- Stream responses to disk and validate status codes.

## Resilience & Observability
- Wrap HTTP calls in retries for transient failures (`tenacity` or custom retry loop).
- Log crawler progress with `logging` so future services can integrate with e.g., CloudWatch.
- Return structured results for metrics (counts of announcements, attachments downloaded, failures).

## Testing Approach
- Introduce unit tests with `responses` (requests mocking) to simulate list/detail pages and attachment downloads.
- Validate pagination parsing, detail link extraction, and attachment handling without requiring live HTTP access.

## Future Extensions
- Persist metadata to a database or message bus.
- Enrich metadata with eligibility rules for personalization engine.
- Expand crawler family for SH, GH, or other agencies by sharing a `BaseCrawler` helper in `src/common/http.py`.

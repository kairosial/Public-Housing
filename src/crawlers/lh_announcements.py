"""Crawler for LH rental housing announcements and attachment PDFs."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)

LIST_URL = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026"
DETAIL_URL = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancDetail.do"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0.0.0 Safari/537.36"
)


@dataclass
class Attachment:
    """Metadata for an attachment file."""

    name: str
    url: str
    local_path: Optional[Path] = None


@dataclass
class Announcement:
    """Represents a single LH announcement."""

    identifier: str
    title: str
    detail_url: Optional[str]
    metadata: Dict[str, str] = field(default_factory=dict)
    attachments: List[Attachment] = field(default_factory=list)
    request_payload: Optional[Dict[str, str]] = None

    def slug(self) -> str:
        """Return a filesystem-safe identifier for the announcement."""

        base = self.identifier or self.title
        slug = re.sub(r"[^A-Za-z0-9가-힣]+", "-", base).strip("-")
        if not slug:
            slug = "announcement"
        return slug[:80]


class LHAnnouncementCrawler:
    """Crawler capable of downloading LH announcement PDFs."""

    def __init__(
        self,
        list_url: str = LIST_URL,
        detail_url: str = DETAIL_URL,
        output_dir: Path | str = Path("assets/lh/pdfs"),
        delay_seconds: float = 1.0,
        session: Optional[requests.Session] = None,
        max_pages: Optional[int] = None,
    ) -> None:
        self.list_url = list_url
        self.detail_url = detail_url
        self.output_dir = Path(output_dir)
        self.delay_seconds = delay_seconds
        self.session = session or self._build_session()
        self.max_pages = max_pages

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
        return session

    def crawl(self) -> List[Announcement]:
        """Run the crawler end-to-end, returning announcements with attachments."""

        announcements: List[Announcement] = []
        page_index = 1
        while True:
            if self.max_pages and page_index > self.max_pages:
                break

            LOGGER.info("Fetching announcement page %s", page_index)
            html = self.fetch_list_page(page_index)
            page_announcements, has_next_page = self.parse_list_page(html)
            if not page_announcements:
                LOGGER.info("No announcements discovered on page %s; stopping.", page_index)
                break

            for announcement in page_announcements:
                try:
                    attachments = self.fetch_attachments(announcement)
                except Exception as exc:  # pragma: no cover - best effort logging
                    LOGGER.exception("Failed to fetch attachments for %s: %s", announcement.identifier, exc)
                    continue
                announcement.attachments = attachments

                for attachment in announcement.attachments:
                    try:
                        self.download_attachment(announcement, attachment)
                    except Exception as exc:  # pragma: no cover - best effort logging
                        LOGGER.exception(
                            "Failed to download attachment %s for %s: %s",
                            attachment.url,
                            announcement.identifier,
                            exc,
                        )
                announcements.append(announcement)

            if not has_next_page:
                break

            page_index += 1
            time.sleep(self.delay_seconds)

        return announcements

    def fetch_list_page(self, page_index: int) -> str:
        """Retrieve the raw HTML for a list page."""

        payload = {"pageIndex": page_index}
        response = self.session.get(self.list_url, params=payload, timeout=30)
        response.raise_for_status()
        self._ensure_encoding(response)
        return response.text

    def parse_list_page(self, html: str) -> tuple[List[Announcement], bool]:
        """Parse a list page into announcements and a pagination flag."""

        soup = BeautifulSoup(html, "html.parser")
        announcements: List[Announcement] = []

        table_rows = soup.select("table tbody tr")
        for row in table_rows:
            link = row.find("a", href=True)
            if not link:
                continue

            title = link.get_text(strip=True)
            identifier = link.get("data-id") or link.get("id") or title
            detail_url, payload = self._resolve_detail_target(link)

            metadata: Dict[str, str] = {}
            cells = row.find_all("td")
            for index, cell in enumerate(cells):
                key = f"col_{index}"
                metadata[key] = cell.get_text(strip=True)

            announcements.append(
                Announcement(
                    identifier=identifier,
                    title=title,
                    detail_url=detail_url,
                    metadata=metadata,
                    request_payload=payload,
                )
            )

        has_next = self._detect_has_next_page(soup)
        return announcements, has_next

    def fetch_attachments(self, announcement: Announcement) -> List[Attachment]:
        """Fetch the detail page for an announcement and parse attachments."""

        detail_html = self.fetch_detail_page(announcement)
        if not detail_html:
            return []

        soup = BeautifulSoup(detail_html, "html.parser")
        attachments: List[Attachment] = []

        for anchor in soup.select("a[href]"):
            href = anchor["href"]
            if not href.lower().endswith(".pdf"):
                continue
            attachment_url = urljoin(self.detail_url, href)
            attachments.append(
                Attachment(
                    name=anchor.get_text(strip=True) or Path(attachment_url).name,
                    url=attachment_url,
                )
            )

        return attachments

    def fetch_detail_page(self, announcement: Announcement) -> Optional[str]:
        """Retrieve the detail page HTML for a single announcement."""

        if announcement.detail_url:
            response = self.session.get(announcement.detail_url, timeout=30)
        elif announcement.request_payload:
            response = self.session.post(self.detail_url, data=announcement.request_payload, timeout=30)
        else:
            LOGGER.warning("Announcement %s lacks detail information", announcement.identifier)
            return None

        response.raise_for_status()
        self._ensure_encoding(response)
        return response.text

    def download_attachment(self, announcement: Announcement, attachment: Attachment) -> Path:
        """Download an attachment to disk if missing, returning its local path."""

        announcement_dir = self.output_dir / announcement.slug()
        announcement_dir.mkdir(parents=True, exist_ok=True)
        filename = attachment.name
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        destination = announcement_dir / self._sanitize_filename(filename)

        if destination.exists():
            LOGGER.debug("Skipping existing file %s", destination)
            attachment.local_path = destination
            return destination

        LOGGER.info("Downloading %s", attachment.url)
        with self.session.get(attachment.url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(destination, "wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)

        attachment.local_path = destination
        return destination

    @staticmethod
    def _ensure_encoding(response: requests.Response) -> None:
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9가-힣_.-]+", "_", name).strip("_")
        return cleaned or "attachment.pdf"

    def _resolve_detail_target(self, link) -> tuple[Optional[str], Optional[Dict[str, str]]]:
        href = link.get("href", "")
        if href and not href.startswith("javascript:"):
            return urljoin(self.list_url, href), None

        js_target = href or ""
        match = re.search(r"fn[_a-zA-Z]*\(([^)]+)\)", js_target)
        if not match:
            return None, None

        raw_args = match.group(1)
        args = [arg.strip("' ") for arg in raw_args.split(",")]
        payload_keys = ["panId", "panDtlSeq", "notiSeq", "bbsSeq"]
        payload = {key: value for key, value in zip(payload_keys, args)}
        payload = {k: v for k, v in payload.items() if v}
        return None, payload or None

    def _detect_has_next_page(self, soup: BeautifulSoup) -> bool:
        pagination_candidates = soup.select("ul.pagination li") or soup.select("div.pagination a")
        keywords = {"next", "다음", ">"}
        for element in pagination_candidates:
            label = element.get_text(strip=True).lower()
            if not any(keyword in label for keyword in keywords):
                continue

            if getattr(element, "name", "") == "li":
                if "disabled" in element.get("class", []):
                    continue
                anchor = element.find("a", href=True)
                if anchor:
                    return True
            elif getattr(element, "name", "") == "a":
                if element.get("class") and "disabled" in element.get("class"):
                    continue
                return bool(element.get("href"))

        return False


def main(argv: Optional[Sequence[str]] = None) -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Crawl LH announcements and download PDFs")
    parser.add_argument("--output", type=Path, default=Path("assets/lh/pdfs"), help="Directory to store PDFs")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between page requests (seconds)")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional max number of pages to crawl")
    parser.add_argument("--metadata", type=Path, help="Optional path to JSON file for metadata export")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    crawler = LHAnnouncementCrawler(output_dir=args.output, delay_seconds=args.delay, max_pages=args.max_pages)
    announcements = crawler.crawl()

    if args.metadata:
        serialisable = [
            {
                "identifier": announcement.identifier,
                "title": announcement.title,
                "detail_url": announcement.detail_url,
                "metadata": announcement.metadata,
                "attachments": [
                    {
                        "name": attachment.name,
                        "url": attachment.url,
                        "local_path": str(attachment.local_path) if attachment.local_path else None,
                    }
                    for attachment in announcement.attachments
                ],
            }
            for announcement in announcements
        ]
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(json.dumps(serialisable, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("Wrote metadata to %s", args.metadata)


if __name__ == "__main__":  # pragma: no cover
    main()

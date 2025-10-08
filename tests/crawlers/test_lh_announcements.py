import json
from pathlib import Path

import pytest
import responses

from src.crawlers.lh_announcements import (
    Announcement,
    LHAnnouncementCrawler,
)


FIXTURES = Path(__file__).parents[1] / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_list_page_extracts_announcements():
    crawler = LHAnnouncementCrawler()
    html = load_fixture("lh_list_page.html")

    announcements, has_next = crawler.parse_list_page(html)

    assert has_next is True
    assert len(announcements) == 2

    seoul = announcements[0]
    assert seoul.title == "서울 청년 전세임대"
    assert seoul.detail_url.endswith("panId=2024-001&panDtlSeq=1")

    gyeonggi = announcements[1]
    assert gyeonggi.request_payload
    assert gyeonggi.request_payload["panId"] == "2024-002"
    assert gyeonggi.request_payload["panDtlSeq"] == "2"
    assert gyeonggi.request_payload["notiSeq"] == "10"
    assert gyeonggi.request_payload["bbsSeq"] == "5"


@responses.activate
def test_fetch_attachments_filters_pdf_only():
    detail_html = load_fixture("lh_detail_page.html")
    detail_url = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancDetail.do?panId=2024-001&panDtlSeq=1"

    responses.add(responses.GET, detail_url, body=detail_html, status=200)

    crawler = LHAnnouncementCrawler()
    announcement = Announcement(
        identifier="2024-001",
        title="서울 청년 전세임대",
        detail_url=detail_url,
    )

    attachments = crawler.fetch_attachments(announcement)

    assert len(attachments) == 3
    assert attachments[0].name == "공고문.pdf"
    assert attachments[0].url.endswith("lfhFile.do?fileId=abc123")
    assert attachments[1].name == "안내문.PDF"
    assert attachments[1].url.endswith("common/fileDownload.do?fileKey=xyz987")
    assert attachments[2].name == "brochure.PDF"
    assert attachments[2].url.endswith("filename=brochure.PDF")


@responses.activate
def test_crawl_downloads_attachments(tmp_path):
    list_html = load_fixture("lh_list_page.html")
    empty_html = """<html><body><table><tbody></tbody></table></body></html>"""

    list_url = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026&pageIndex=1"
    next_url = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026&pageIndex=2"

    responses.add(responses.GET, list_url, body=list_html, status=200)
    responses.add(responses.GET, next_url, body=empty_html, status=200)

    detail_url = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancDetail.do?panId=2024-001&panDtlSeq=1"
    responses.add(responses.GET, detail_url, body=load_fixture("lh_detail_page.html"), status=200)

    responses.add(
        responses.POST,
        "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancDetail.do",
        body=load_fixture("lh_detail_page.html"),
        status=200,
    )

    responses.add(
        responses.GET,
        "https://apply.lh.or.kr/lhapply/lfhFile.do?fileId=abc123",
        body=b"%PDF-1.4",
        status=200,
        content_type="application/pdf",
    )
    responses.add(
        responses.GET,
        "https://apply.lh.or.kr/common/fileDownload.do?fileKey=xyz987",
        body=b"%PDF-1.4",
        status=200,
        content_type="application/pdf",
    )
    responses.add(
        responses.GET,
        "https://apply.lh.or.kr/file/download?uuid=qwe555&filename=brochure.PDF",
        body=b"%PDF-1.4",
        status=200,
        content_type="application/pdf",
    )

    crawler = LHAnnouncementCrawler(output_dir=tmp_path, delay_seconds=0, max_pages=2)
    announcements = crawler.crawl()

    assert len(announcements) == 2

    seoul_dir = tmp_path / announcements[0].slug()
    assert seoul_dir.exists()
    downloaded = list(seoul_dir.iterdir())
    assert len(downloaded) == 3

    metadata_dump = tmp_path / "metadata.json"
    metadata_dump.write_text(json.dumps({"count": len(announcements)}), encoding="utf-8")


if __name__ == "__main__":
    pytest.main()

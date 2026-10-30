"""End-to-end tests that run the full pipeline against captured pages.

The fixtures under ``test/fixtures`` are trimmed copies of real responses (see
``test/fixtures/README.md``). Requests are served from those files, so these
tests exercise config loading, list parsing, article parsing, robots handling
and storage without touching the network.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from web_harvester.core import Response
from web_harvester.core.engine import CrawlerEngine
from web_harvester.core.http_client.base import BaseHttpClient
from web_harvester.core.request import Request
from web_harvester.crawler.site_crawler import SiteCrawler
from web_harvester.storage.json_storage import JSONStorage
from web_harvester.utils.config import Settings, load_site_config

FIXTURES = Path(__file__).parent / "fixtures"

# (URL prefix, fixture path); the first matching prefix wins.
Routes = List[Tuple[str, str]]


class FixtureClient(BaseHttpClient):
    """HTTP client that serves captured fixtures instead of network traffic."""

    def __init__(self, routes: Routes):
        self._routes = routes
        self.requested: List[str] = []

    def _fixture_for(self, url: str) -> Optional[Path]:
        for prefix, relative in self._routes:
            if url.startswith(prefix):
                return FIXTURES / relative
        return None

    def fetch_sync(self, request: Request) -> Response:
        self.requested.append(request.url)
        fixture = self._fixture_for(request.url)
        if fixture is None:
            if request.url.endswith("/robots.txt"):
                return Response(url=request.url, status_code=404, request=request)
            raise AssertionError(f"unexpected network request: {request.url}")
        return Response(
            url=request.url,
            status_code=200,
            text=fixture.read_text(encoding="utf-8"),
            request=request,
        )

    async def fetch_async(self, request: Request) -> Response:
        return self.fetch_sync(request)


def run_site(
    site_id: str,
    routes: Routes,
    output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    **limit_overrides: object,
) -> Tuple[List, FixtureClient, Dict]:
    settings = Settings()
    settings.set("engine.mode", "sync")
    settings.set("engine.download_delay", 0)

    client = FixtureClient(routes)
    monkeypatch.setattr(
        "web_harvester.core.engine.build_http_client", lambda _settings: client
    )

    engine = CrawlerEngine(settings, skip_seen_urls=False)
    engine.add_storage(JSONStorage(output_dir=str(output_dir), batch_mode=True))

    site_config = load_site_config(site_id)
    overrides = {"max_items": 10, "max_pages": 1, "timeout": 60, **limit_overrides}
    crawler = SiteCrawler(
        site_config,
        default_limits=settings.get("limits", {}),
        limit_overrides=overrides,
    )
    items = engine.run(crawler)
    return items, client, site_config


CNA_ROUTES: Routes = [
    ("https://www.cna.com.tw/news/", "cna/article.html"),
    ("https://www.cna.com.tw/cna2018api/api/WNewsList", "cna/list_page.json"),
]

SETN_ROUTES: Routes = [
    ("https://www.setn.com/news/getlastestnews/", "setn/list_page.html"),
    ("https://www.setn.com/news/", "setn/article.html"),
]


def cna_list_urls() -> List[str]:
    payload = json.loads((FIXTURES / "cna" / "list_page.json").read_text(encoding="utf-8"))
    return [entry["PageUrl"] for entry in payload["ResultData"]["Items"]]


class TestCNASite:
    def test_collects_articles_from_json_list(self, tmp_path, monkeypatch):
        items, client, site_config = run_site("cna", CNA_ROUTES, tmp_path, monkeypatch)

        expected = [url for url in cna_list_urls() if "netzero.cna.com.tw" not in url]
        assert len(items) == len(expected)
        assert [item.url for item in items] == expected
        assert all(item.source == site_config["name"] for item in items)

    def test_article_fields_are_normalised(self, tmp_path, monkeypatch):
        items, _, _ = run_site("cna", CNA_ROUTES, tmp_path, monkeypatch)

        for item in items:
            assert item.data["title"]
            assert item.data["content"]
            assert isinstance(item.data["published_at"], datetime)
            assert item.data["author"]

    def test_netzero_links_are_never_requested(self, tmp_path, monkeypatch):
        items, client, _ = run_site("cna", CNA_ROUTES, tmp_path, monkeypatch)

        assert any("netzero.cna.com.tw" in url for url in cna_list_urls()), (
            "fixture must contain a netzero link so the exclusion rule is exercised"
        )
        assert all("netzero.cna.com.tw" not in url for url in client.requested)
        assert all("netzero.cna.com.tw" not in item.url for item in items)

    def test_records_are_written_to_json(self, tmp_path, monkeypatch):
        items, _, site_config = run_site("cna", CNA_ROUTES, tmp_path, monkeypatch)

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert files[0].name.startswith(site_config["name"])
        records = json.loads(files[0].read_text(encoding="utf-8"))
        assert [record["url"] for record in records] == [item.url for item in items]


class TestSETNSite:
    def test_collects_articles_from_html_list(self, tmp_path, monkeypatch):
        items, client, site_config = run_site("setn", SETN_ROUTES, tmp_path, monkeypatch)

        assert len(items) == 4
        assert all(item.source == site_config["name"] for item in items)
        assert all("/news/" in item.url for item in items)
        assert client.requested[0].endswith("robots.txt")

    def test_article_fields_are_normalised(self, tmp_path, monkeypatch):
        items, _, _ = run_site("setn", SETN_ROUTES, tmp_path, monkeypatch)

        for item in items:
            assert item.data["title"]
            assert item.data["content"]
            assert isinstance(item.data["published_at"], datetime)
            assert item.data["category"]

    def test_robots_txt_is_requested_once_per_origin(self, tmp_path, monkeypatch):
        _, client, _ = run_site("setn", SETN_ROUTES, tmp_path, monkeypatch)

        robots = [url for url in client.requested if url.endswith("/robots.txt")]
        assert robots == ["https://www.setn.com/robots.txt"]

    def test_pagination_stops_at_one_page(self, tmp_path, monkeypatch):
        _, client, _ = run_site("setn", SETN_ROUTES, tmp_path, monkeypatch)

        list_requests = [url for url in client.requested if "getlastestnews" in url]
        assert list_requests == ["https://www.setn.com/news/getlastestnews/1/1"]

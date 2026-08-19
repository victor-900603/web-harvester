from __future__ import annotations

from datetime import datetime

from src.core import Item, Request
from src.crawler import SiteCrawler
from conftest import make_response


class TestStartRequests:
    def test_pagination_generates_pages(self, sample_site_config):
        del sample_site_config["limits"]["max_pages"]
        crawler = SiteCrawler(sample_site_config)
        urls = [r.url for r in crawler.start_requests()]
        assert urls == [
            "https://example.com/news?page=1",
            "https://example.com/news?page=2",
            "https://example.com/news?page=3",
        ]
        assert all(r.callback == "parse_list" for r in crawler.start_requests())

    def test_limits_max_pages_caps_pagination(self, sample_site_config):
        sample_site_config["limits"]["max_pages"] = 2
        crawler = SiteCrawler(sample_site_config)
        urls = [r.url for r in crawler.start_requests()]
        assert urls == [
            "https://example.com/news?page=1",
            "https://example.com/news?page=2",
        ]

    def test_no_pagination_yields_single_request(self, sample_site_config):
        sample_site_config["list_page"]["pagination"]["enabled"] = False
        crawler = SiteCrawler(sample_site_config)
        urls = [r.url for r in crawler.start_requests()]
        assert urls == ["https://example.com/news?page={page}"]

    def test_site_request_headers_carried_over(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        req = next(crawler.start_requests())
        assert req.headers == {"Referer": "https://example.com"}

    def test_list_method_defaults_to_get(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        req = next(crawler.start_requests())
        assert req.method == "GET"

    def test_list_method_post_from_config(self, sample_site_config):
        sample_site_config["list_page"]["method"] = "POST"
        crawler = SiteCrawler(sample_site_config)
        reqs = list(crawler.start_requests())
        assert len(reqs) == 2
        assert all(r.method == "POST" for r in reqs)

    def test_limits_property(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        assert crawler.limits["max_pages"] == 2
        assert crawler.limits["max_items"] == 10


class TestParseList:
    def test_non_ok_list_yields_nothing(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news?page=1",
            "<article class='news-item'><a href='/news/1'>One</a></article>",
            status_code=403,
        )
        results = list(crawler.parse_list(resp))
        assert results == []

    def test_html_list_yields_absolute_url_requests(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news?page=1",
            "<article class='news-item'><a href='/news/1'>One</a></article>"
            "<article class='news-item'><a href='/news/2'>Two</a></article>",
        )
        results = list(crawler.parse_list(resp))
        assert len(results) == 2
        assert all(isinstance(r, Request) for r in results)
        assert results[0].url == "https://example.com/news/1"
        assert results[1].url == "https://example.com/news/2"
        assert all(r.callback == "parse_article" for r in results)

    def test_html_list_without_article_config_yields_items(self, sample_site_config):
        sample_site_config["article_page"] = {}
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news?page=1",
            "<article class='news-item'><a href='/news/1'>One</a></article>",
        )
        results = list(crawler.parse_list(resp))
        assert len(results) == 1
        item = results[0]
        assert isinstance(item, Item)
        assert item.url == "https://example.com/news/1"
        assert item.item_type == "link"

    def test_json_list_yields_requests_with_template(self, sample_site_config):
        sample_site_config["list_page"] = {
            "url": "https://example.com/api",
            "type": "json",
            "selectors": {
                "items": "data.articles",
                "url_field": "slug",
                "url_template": "https://example.com{url}",
            },
        }
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/api",
            '{"data": {"articles": [{"slug": "/a/1"}, {"slug": "/a/2"}]}}',
        )
        results = list(crawler.parse_list(resp))
        assert len(results) == 2
        assert results[0].url == "https://example.com/a/1"
        assert results[1].url == "https://example.com/a/2"


class TestParseArticle:
    def test_non_ok_article_yields_nothing(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news/1",
            "<h1 class='article-title'>Title</h1>",
            status_code=404,
        )
        results = list(crawler.parse_article(resp))
        assert results == []

    def test_html_article_extracts_fields(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news/1",
            "<h1 class='article-title'>Title</h1>"
            "<div class='article-body'>Body text</div>"
            "<time class='publish-date' datetime='2026-08-19T10:00:00'>x</time>"
            "<span class='author-name'>Alice</span>",
        )
        item = next(crawler.parse_article(resp))
        assert isinstance(item, Item)
        assert item.data["title"] == "Title"
        assert item.data["content"] == "Body text"
        assert item.data["author"] == "Alice"
        assert isinstance(item.data["published_at"], datetime)
        assert item.data["published_at"].year == 2026
        assert item.url == "https://example.com/news/1"
        assert item.item_type == "article"

    def test_json_article_extracts_fields(self, sample_site_config):
        sample_site_config["article_page"] = {
            "type": "json",
            "selectors": {
                "title": "data.title",
                "content": {"type": "text", "path": "data.content"},
            },
        }
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/api/1",
            '{"data": {"title": "T", "content": "C"}}',
        )
        item = next(crawler.parse_article(resp))
        assert item.data["title"] == "T"
        assert item.data["content"] == "C"

    def test_extract_field_datetime_without_format(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        value = crawler._extract_field("2026-08-19T10:00:00", {"type": "datetime"})
        assert isinstance(value, datetime)

    def test_extract_field_regex(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        value = crawler._extract_field("id-123", {"type": "text", "regex": r"(\d+)"})
        assert value == "123"

    def test_extract_field_returns_raw_value_on_error(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        value = crawler._extract_field("not-a-date", {"type": "datetime", "datetime_format": "%Y"})
        assert value == "not-a-date"

    def test_html_field_missing_selector_skipped(self, sample_site_config):
        sample_site_config["article_page"] = {
            "type": "html",
            "selectors": {
                "title": {"type": "text"},
                "content": "h1.article-title",
            },
        }
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news/1",
            "<h1 class='article-title'>Title</h1>",
        )
        item = next(crawler.parse_article(resp))
        assert item.data == {
            "url": "https://example.com/news/1",
            "content": "Title",
        }
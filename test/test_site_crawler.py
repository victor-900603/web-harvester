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
        assert urls == ["https://example.com/news?page=1"]

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


class TestBuildListUrl:
    def test_page_placeholder_filled(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        assert crawler._build_list_url(page_num=2) == "https://example.com/news?page=2"

    def test_keyword_uses_search_block(self, sample_site_config):
        sample_site_config["list_page"]["search"] = {
            "url": "https://example.com/search?q={keyword}&page={page}",
        }
        crawler = SiteCrawler(sample_site_config, keyword="股市")
        assert crawler._build_list_url(page_num=1) == "https://example.com/search?q=股市&page=1"

    def test_keyword_without_search_block_falls_back(self, sample_site_config):
        sample_site_config["list_page"]["url"] = "https://example.com/news?page={page}"
        crawler = SiteCrawler(sample_site_config, keyword="股市")
        assert crawler._build_list_url(page_num=1) == "https://example.com/news?page=1"

    def test_category_resolved_through_mapping(self, sample_site_config):
        sample_site_config["list_page"]["url"] = "https://example.com/news?cat={category}&page={page}"
        sample_site_config["list_page"]["categories"] = {"股市": "7251", "政治": "6645"}
        crawler = SiteCrawler(sample_site_config, category="股市")
        assert crawler._build_list_url(page_num=1) == "https://example.com/news?cat=7251&page=1"

    def test_category_not_in_mapping_uses_raw_name(self, sample_site_config):
        sample_site_config["list_page"]["url"] = "https://example.com/news?cat={category}&page={page}"
        sample_site_config["list_page"]["categories"] = {"股市": "7251"}
        crawler = SiteCrawler(sample_site_config, category="財經")
        assert crawler._build_list_url(page_num=1) == "https://example.com/news?cat=財經&page=1"

    def test_category_default_when_not_given(self, sample_site_config):
        sample_site_config["list_page"]["url"] = "https://example.com/news?cat={category}&page={page}"
        sample_site_config["list_page"]["category_default"] = "0"
        crawler = SiteCrawler(sample_site_config)
        assert crawler._build_list_url(page_num=1) == "https://example.com/news?cat=0&page=1"

    def test_keyword_and_category_combined(self, sample_site_config):
        sample_site_config["list_page"]["search"] = {
            "url": "https://example.com/search?q={keyword}&cat={category}&page={page}",
        }
        sample_site_config["list_page"]["categories"] = {"股市": "7251"}
        crawler = SiteCrawler(sample_site_config, keyword="台股", category="股市")
        assert crawler._build_list_url(page_num=1) == "https://example.com/search?q=台股&cat=7251&page=1"

    def test_keyword_and_category_unrepresentable_skipped(self, sample_site_config):
        sample_site_config["list_page"]["search"] = {
            "url": "https://example.com/search?q={keyword}&page={page}",
        }
        sample_site_config["list_page"]["categories"] = {"股市": "7251"}
        crawler = SiteCrawler(sample_site_config, keyword="台股", category="股市")
        assert crawler._build_list_url(page_num=1) is None

    def test_missing_placeholder_left_untouched(self, sample_site_config):
        sample_site_config["list_page"]["url"] = "https://example.com/news?page={page}"
        crawler = SiteCrawler(sample_site_config)
        assert crawler._build_list_url() == "https://example.com/news?page=1"


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

    def test_search_selectors_override_list_selectors(self, sample_site_config):
        sample_site_config["list_page"] = {
            "url": "https://example.com/api?page={page}",
            "type": "json",
            "selectors": {
                "items": "lists",
                "url_field": "titleLink",
                "url_template": "https://example.com{url}",
            },
            "search": {
                "url": "https://example.com/api?page={page}&q={keyword}",
                "type": "json",
                "selectors": {
                    "items": "lists",
                    "url_field": "titleLink",
                    "url_template": "{url}",
                },
            },
        }
        crawler = SiteCrawler(sample_site_config, keyword="股市")
        resp = make_response(
            "https://example.com/api?page=1&q=股市",
            '{"lists": [{"titleLink": "https://example.com/news/1"}]}',
        )
        results = list(crawler.parse_list(resp))
        assert len(results) == 1
        assert results[0].url == "https://example.com/news/1"


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

    def test_article_category_from_meta(self, sample_site_config):
        sample_site_config["category"] = {
            "sources": [{"type": "meta", "name": "section"}],
        }
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news/1",
            "<meta name='section' content='股市'>"
            "<h1 class='article-title'>Title</h1>",
        )
        item = next(crawler.parse_article(resp))
        assert item.data["category"] == ["股市"]

    def test_article_category_default_fallback(self, sample_site_config):
        sample_site_config["category"] = {
            "sources": [{"type": "meta", "name": "section"}],
            "default": "其他",
        }
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news/1",
            "<h1 class='article-title'>Title</h1>",
        )
        item = next(crawler.parse_article(resp))
        assert item.data["category"] == ["其他"]

    def test_article_tags_from_meta_split(self, sample_site_config):
        sample_site_config["tags"] = {
            "sources": [{"type": "meta", "name": "news_keywords", "split": ","}],
        }
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news/1",
            "<meta name='news_keywords' content='台股,科技股'>"
            "<h1 class='article-title'>Title</h1>",
        )
        item = next(crawler.parse_article(resp))
        assert item.data["tags"] == ["台股", "科技股"]

    def test_article_classification_list_data_source(self, sample_site_config):
        sample_site_config["category"] = {
            "sources": [{"type": "list_data", "path": "cate_id"}],
        }
        crawler = SiteCrawler(sample_site_config)
        request = Request(
            url="https://example.com/news/1",
            callback="parse_article",
            meta={"list_data": {"cate_id": "7251"}},
        )
        resp = make_response("https://example.com/news/1", "<h1 class='article-title'>Title</h1>")
        resp.request = request
        item = next(crawler.parse_article(resp))
        assert item.data["category"] == ["7251"]

    def test_article_no_classification_config(self, sample_site_config):
        crawler = SiteCrawler(sample_site_config)
        resp = make_response(
            "https://example.com/news/1",
            "<h1 class='article-title'>Title</h1>",
        )
        item = next(crawler.parse_article(resp))
        assert "category" not in item.data
        assert "tags" not in item.data
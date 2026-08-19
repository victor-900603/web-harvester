from __future__ import annotations

from src.parsers import HTMLParser, JSONParser


class TestHTMLParser:
    def test_select_returns_matching_tags(self, sample_html):
        parser = HTMLParser(sample_html, parser="html.parser")
        items = parser.select("article.news-item")
        assert len(items) == 2

    def test_select_one(self, sample_html):
        parser = HTMLParser(sample_html, parser="html.parser")
        assert parser.select_one("h1.article-title").get_text() == "Test Title"
        assert parser.select_one("p.nonexistent") is None

    def test_extract_text(self, sample_html):
        parser = HTMLParser(sample_html, parser="html.parser")
        assert parser.extract_text("h1.article-title") == "Test Title"
        assert parser.extract_text("p.nonexistent") is None

    def test_extract_attribute(self, sample_html):
        parser = HTMLParser(sample_html, parser="html.parser")
        assert parser.extract_attribute("a", "href") == "/news/1"
        assert parser.extract_attribute("p.nonexistent", "href") is None

    def test_extract_text_attribute(self, sample_html):
        parser = HTMLParser(sample_html, parser="html.parser")
        assert parser.extract("h1.article-title", "text") == "Test Title"

    def test_extract_outer_html(self, sample_html):
        parser = HTMLParser(sample_html, parser="html.parser")
        html = parser.extract("span.author-name", "outer_html")
        assert html == "<span class=\"author-name\">Alice</span>"

    def test_extract_inner_html(self, sample_html):
        parser = HTMLParser(sample_html, parser="html.parser")
        assert parser.extract("span.author-name", "inner_html") == "Alice"

    def test_extract_default_attribute(self, sample_html):
        parser = HTMLParser(sample_html, parser="html.parser")
        assert parser.extract("time.publish-date", "datetime") == "2026-08-19T10:00:00"

    def test_extract_all_text(self, sample_html):
        parser = HTMLParser(sample_html, parser="html.parser")
        assert parser.extract_all_text("article.news-item") == "One Two"
        assert parser.extract_all_text("p.nonexistent") is None


class TestJSONParser:
    def test_init_with_string(self):
        parser = JSONParser('{"name": "Alice", "age": 30}')
        assert parser.data == {"name": "Alice", "age": 30}

    def test_init_with_object(self):
        data = {"items": [{"title": "A"}]}
        parser = JSONParser(data)
        assert parser.data is data

    def test_extract_path_nested_dict(self):
        parser = JSONParser('{"user": {"name": "Alice"}}')
        assert parser.extract_path("user.name") == "Alice"

    def test_extract_path_list_index(self):
        parser = JSONParser('{"items": [{"title": "A"}, {"title": "B"}]}')
        assert parser.extract_path("items.1.title") == "B"

    def test_extract_path_missing_returns_none(self):
        parser = JSONParser('{"user": {"name": "Alice"}}')
        assert parser.extract_path("user.age") is None
        assert parser.extract_path("missing.key") is None
        assert parser.extract_path("items.5") is None

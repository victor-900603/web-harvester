from __future__ import annotations

import json as json_lib
from datetime import datetime, timezone

from src.core import Item, Request, Response


class TestRequest:
    def test_defaults(self):
        req = Request(url="https://example.com")
        assert req.method == "GET"
        assert req.headers == {}
        assert req.callback is None

    def test_copy_is_independent(self):
        req = Request(
            url="https://example.com",
            headers={"a": "1"},
            cookies={"c": "2"},
            params={"p": "3"},
            meta={"m": "4"},
        )
        copied = req.copy()
        assert copied.url == req.url
        copied.headers["a"] = "changed"
        copied.cookies["c"] = "changed"
        copied.params["p"] = "changed"
        copied.meta["m"] = "changed"
        assert req.headers["a"] == "1"
        assert req.cookies["c"] == "2"
        assert req.params["p"] == "3"
        assert req.meta["m"] == "4"

    def test_copy_preserves_fields(self):
        req = Request(url="https://example.com", method="POST", callback="parse_article")
        copied = req.copy()
        assert copied.method == "POST"
        assert copied.callback == "parse_article"


class TestResponse:
    def test_ok(self):
        assert Response(url="u", status_code=200).ok
        assert Response(url="u", status_code=404).ok is False

    def test_content_bytes(self):
        resp = Response(url="u", status_code=200, text="hi")
        assert resp.content == b"hi"

    def test_content_none_when_empty(self):
        assert Response(url="u", status_code=200).content is None

    def test_meta_from_request(self):
        req = Request(url="u", meta={"page": 2})
        resp = Response(url="u", status_code=200, request=req)
        assert resp.meta == {"page": 2}

    def test_meta_none_without_request(self):
        resp = Response(url="u", status_code=200)
        assert resp.meta is None

    def test_json_parses_body(self):
        payload = json_lib.dumps({"ok": True})
        resp = Response(url="u", status_code=200, body=payload)
        assert resp.json() == {"ok": True}

    def test_json_none_without_body(self):
        resp = Response(url="u", status_code=200)
        assert resp.json() is None


class TestItem:
    def test_to_dict_merges_fields(self):
        item = Item(
            data={"title": "Hello", "tags": ["a", "b"]},
            source="example",
            url="https://example.com/a",
            item_type="article",
        )
        result = item.to_dict()
        assert result["source"] == "example"
        assert result["url"] == "https://example.com/a"
        assert result["item_type"] == "article"
        assert result["title"] == "Hello"
        assert isinstance(result["crawler_at"], datetime)
        assert result["crawler_at"].tzinfo is timezone.utc

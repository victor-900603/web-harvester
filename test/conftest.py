from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import Item, Request, Response


@pytest.fixture
def sample_html() -> str:
    return """
    <html>
      <body>
        <h1 class="article-title">Test Title</h1>
        <div class="article-body">Hello world</div>
        <time class="publish-date" datetime="2026-08-19T10:00:00">2026-08-19T10:00:00</time>
        <span class="author-name">Alice</span>
        <article class="news-item"><a href="/news/1">One</a></article>
        <article class="news-item"><a href="/news/2">Two</a></article>
        <a href="/other">Other</a>
      </body>
    </html>
    """


@pytest.fixture
def sample_site_config() -> dict:
    return {
        "name": "example",
        "base_url": "https://example.com",
        "limits": {
            "max_items": 10,
            "max_pages": 2,
            "stop_on_duplicate": False,
            "timeout": 60,
        },
        "request": {
            "headers": {"Referer": "https://example.com"},
            "cookies": {},
        },
        "list_page": {
            "type": "html",
            "selectors": {"items": "article.news-item", "link": "a", "link_attr": "href"},
            "pagination": {"enabled": True, "start": 1},
            "sources": [
                {"url": "https://example.com/news?page={page}"},
            ],
        },
        "article_page": {
            "type": "html",
            "selectors": {
                "title": "h1.article-title",
                "content": {"type": "text", "selector": "div.article-body", "attr": "text"},
                "published_at": {
                    "type": "datetime",
                    "selector": "time.publish-date",
                    "attr": "datetime",
                    "datetime_format": "%Y-%m-%dT%H:%M:%S",
                },
                "author": {"type": "text", "selector": "span.author-name", "attr": "text"},
            },
        },
    }


def make_response(url: str, text: str = "", status_code: int = 200) -> Response:
    return Response(url=url, status_code=status_code, text=text)


def make_item(url: str = "https://example.com/a", **data) -> Item:
    return Item(data={"title": "T", **data}, source="example", url=url)

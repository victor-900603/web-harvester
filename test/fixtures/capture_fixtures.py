"""Refresh the captured pages used by ``test/test_integration_offline.py``.

This script talks to the live sites, so it is meant to be run by hand when a
site changes its markup:

    python test/fixtures/capture_fixtures.py

It rewrites ``cna/`` and ``setn/`` under this directory. Trimming rules are
documented in ``README.md``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as creq

OUT = Path(__file__).resolve().parent
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CNA_LIST_URL = "https://www.cna.com.tw/cna2018api/api/WNewsList"
SETN_LIST_URL = "https://www.setn.com/news/getlastestnews/1/1"


def fetch(url: str, *, method: str = "GET", headers: Optional[Dict[str, str]] = None, **kwargs: Any):
    merged = {"User-Agent": UA}
    merged.update(headers or {})
    return creq.request(method, url, impersonate="chrome", timeout=40, headers=merged, **kwargs)


def crop_html(
    html: str, selectors: List[str], keep_paragraphs: int = 3, keep_extra: str = ""
) -> str:
    """Keep <head> metadata plus the containers the site config parses."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "noscript", "iframe", "link"]):
        tag.decompose()

    head = soup.head or soup.new_tag("head")
    body = soup.new_tag("body")
    for selector in selectors:
        for element in soup.select(selector):
            if any(element in chosen.descendants for chosen in body.find_all(True)):
                continue
            clone = BeautifulSoup(str(element), "lxml").body
            container = clone.find(element.name, recursive=False) or clone.find()
            for index, paragraph in enumerate(container.find_all("p")):
                if index < keep_paragraphs:
                    continue
                if keep_extra and paragraph.select_one(keep_extra):
                    continue
                paragraph.decompose()
            body.append(container)

    page = BeautifulSoup("<!DOCTYPE html><html></html>", "lxml")
    page.html.append(head)
    page.html.append(body)
    return str(page)


def save(relative: str, text: str) -> None:
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"{relative}: {len(text.encode('utf-8'))} bytes")


def capture_cna() -> None:
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/json",
        "origin": "https://www.cna.com.tw",
        "referer": "https://www.cna.com.tw/list/aall.aspx",
        "x-requested-with": "XMLHttpRequest",
    }
    chosen: List[Dict[str, Any]] = []
    netzero: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = {}
    for page in range(1, 6):
        body = {"action": "0", "category": "aall", "pagesize": "20", "pageidx": str(page)}
        payload = fetch(CNA_LIST_URL, method="POST", data=json.dumps(body), headers=headers).json()
        items = payload["ResultData"]["Items"]
        if not chosen:
            chosen = items[:2]
        netzero = next((item for item in items if "netzero" in item["PageUrl"]), None)
        if netzero:
            break
    if netzero is None:
        raise SystemExit("no netzero.cna.com.tw entry found; exclusion rule would be untested")

    payload["ResultData"]["Items"] = chosen + [netzero]
    save("cna/list_page.json", json.dumps(payload, ensure_ascii=False, indent=2))

    article_url = next(item["PageUrl"] for item in chosen if "netzero" not in item["PageUrl"])
    html = fetch(article_url).text
    save("cna/article.html", crop_html(html, ["div.centralContent"], keep_extra="a.author"))


def capture_setn() -> None:
    soup = BeautifulSoup(fetch(SETN_LIST_URL, headers={"Referer": "https://www.setn.com"}).text, "lxml")
    items = soup.select("div.news_list_item")
    keep = [item for item in items if "www.setn.com/news/" in str(item)]
    if len(keep) < 4:
        raise SystemExit(f"only {len(keep)} www.setn.com items in the list page")
    for dropped in [item for item in items if item not in keep]:
        dropped.decompose()
    for extra in keep[4:]:
        extra.decompose()
    save("setn/list_page.html", str(soup))

    article_url = ""
    for anchor in keep[0].select('a[href*="/news/"]'):
        href = anchor["href"]
        if re.search(r"/news/\d+", href):
            article_url = href if href.startswith("http") else f"https://www.setn.com{href}"
            break
    if not article_url:
        raise SystemExit("could not find an article link in the list page")

    html = fetch(article_url, headers={"Referer": "https://www.setn.com"}).text
    page = crop_html(
        html,
        ["h1.article_title_wrap", "div.article_content_area", "div.time_item", "div.author_wrap"],
    )
    if "article_content_area" not in page or "article_title_wrap" not in page:
        raise SystemExit(f"unexpected article layout: {article_url}")
    save("setn/article.html", page)


if __name__ == "__main__":
    capture_cna()
    capture_setn()

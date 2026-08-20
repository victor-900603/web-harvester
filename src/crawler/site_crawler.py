from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Generator, Union, Any, Dict, Optional
from urllib.parse import urljoin

from ..core import Item, Request, Response
from ..parsers import HTMLParser, JSONParser

from .base import BaseCrawler
from .classifier import Classifier

logger = logging.getLogger(__name__)

class _FormatDict(dict):
    """dict subclass that returns the original placeholder when a key is missing."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class SiteCrawler(BaseCrawler):
    def __init__(
        self,
        site_config: Dict[str, Any],
        category_normalization: Optional[Dict[str, str]] = None,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
    ):
        self._config = site_config
        self.name = site_config.get("name", "unknown")
        self.base_url = site_config.get("base_url", "")
        self._list_cfg = site_config.get("list_page", {})
        self._article_cfg = site_config.get("article_page", {})
        self._request_cfg = site_config.get("request", {})
        self._limits = site_config.get("limits", {})
        self._classifier = Classifier(site_config, category_normalization)
        self._keyword = keyword
        self._category = category
        self._selected_list_cfg: Optional[Dict[str, Any]] = None

    @property
    def limits(self) -> dict:
        """Site-level crawl limits from the configuration."""
        return self._limits

    def _select_list_cfg(self) -> Dict[str, Any]:
        """Return the list_page config to use for the requested keyword/category.

        Sources are matched against the requested filters (keyword/category). A
        source "supports" a filter when its URL contains the matching placeholder.
        Matching precedence:
          1. exact match - the source supports exactly the requested filters
          2. superset    - the source supports all requested filters (and more)
          3. degradation - keep the keyword-supporting source (dropping category)
                          if none, keep a category-supporting source (dropping keyword)
                          if none, fall back to the default source
        The default source is the first one without a {keyword} placeholder.
        This is a pure function of (keyword, category): parse_list re-derives the
        same source when parsing a response without needing request meta.
        """
        if self._selected_list_cfg is not None:
            return self._selected_list_cfg
        sources = self._list_cfg.get("sources", [])
        if not sources:
            logger.warning("'list_page.sources' is empty; using an empty list config.")
            self._selected_list_cfg = dict(self._list_cfg)
            return self._selected_list_cfg

        def supports(src: Dict[str, Any], token: str) -> bool:
            return "{" + token + "}" in src.get("url", "")

        def has_keyword(src: Dict[str, Any]) -> bool:
            return supports(src, "keyword")

        def has_category(src: Dict[str, Any]) -> bool:
            return supports(src, "category")

        def defaults_of(src: Dict[str, Any]) -> Dict[str, Any]:
            base = {k: v for k, v in self._list_cfg.items() if k in ("method", "type", "selectors", "pagination")}
            merged = dict(base)
            for key in ("method", "type", "pagination"):
                if key in src:
                    merged[key] = src[key]
            if "selectors" in src:
                base_selectors = dict(base.get("selectors", {}))
                base_selectors.update(src["selectors"])
                merged["selectors"] = base_selectors
            merged["url"] = src["url"]
            return merged

        default = next((s for s in sources if not has_keyword(s)), sources[0])

        keyword = self._keyword
        category = self._category

        if keyword and category:
            exact = next((s for s in sources if has_keyword(s) and has_category(s)), None)
            if exact:
                result = defaults_of(exact)
            else:
                kw_source = next((s for s in sources if has_keyword(s)), None)
                if kw_source:
                    logger.warning(
                        "Keyword and category requested but no source supports both; "
                        "using a keyword source and ignoring --category."
                    )
                    result = defaults_of(kw_source)
                else:
                    cat_source = next((s for s in sources if has_category(s)), None)
                    if cat_source:
                        logger.warning(
                            "Keyword and category requested but no source supports both; "
                            "using a category source and ignoring --keyword."
                        )
                        result = defaults_of(cat_source)
                    else:
                        logger.warning("Neither keyword nor category is supported by any source; using the default list.")
                        result = defaults_of(default)
        elif keyword:
            exact = next((s for s in sources if has_keyword(s) and not has_category(s)), None)
            if exact:
                result = defaults_of(exact)
            else:
                source = next((s for s in sources if has_keyword(s)), None)
                if source:
                    result = defaults_of(source)
                else:
                    logger.warning("Keyword search requested but no source supports {keyword}; using the default list.")
                    result = defaults_of(default)
        elif category:
            exact = next((s for s in sources if has_category(s) and not has_keyword(s)), None)
            if exact:
                result = defaults_of(exact)
            else:
                source = next((s for s in sources if has_category(s)), None)
                if source:
                    result = defaults_of(source)
                else:
                    logger.warning("Category requested but no source supports {category}; using the default list.")
                    result = defaults_of(default)
        else:
            result = defaults_of(default)
        self._selected_list_cfg = result
        return result

    def _build_list_url(self, page_num: Optional[int] = None) -> Optional[str]:
        """Build a list page URL, filling {page}, {keyword} and {category} placeholders.

        ``category`` is resolved through the ``categories`` mapping (name ->
        in-site value). Unsupported requested filters are dropped with a warning
        instead of aborting the crawl.
        """
        keyword = self._keyword
        category_name = self._category
        cfg = self._select_list_cfg()

        template = cfg.get("url", self.base_url)

        categories = self._list_cfg.get("categories", {})
        category_value = ""
        if category_name:
            category_value = categories.get(category_name)
            if category_value is None:
                logger.warning(
                    f"Category '{category_name}' not found in 'categories', using the raw name as the value."
                )
                category_value = category_name
        elif "{category}" in template:
            category_value = self._list_cfg.get("category_default", "")

        values = _FormatDict(
            keyword=keyword or "",
            category=category_value,
        )
        if page_num is not None:
            values["page"] = page_num
        elif "{page}" in template:
            values["page"] = cfg.get("pagination", {}).get("start", 1)

        return template.format_map(values)

    def start_requests(self) -> Generator[Request, None, None]:
        """Generate initial requests to start crawling the site."""
        cfg = self._select_list_cfg()
        pagination = cfg.get("pagination", {})
        method = cfg.get("method", "GET")

        headers = self._request_cfg.get("headers", {})
        cookies = self._request_cfg.get("cookies", {})

        if pagination.get("enabled", False):
            start = pagination.get("start", 1)
            max_pages = self._limits.get("max_pages", 1)

            for page_num in range(start, start + max_pages):
                url = self._build_list_url(page_num=page_num)
                if url is None:
                    continue
                yield Request(
                    url=url,
                    method=method,
                    headers=headers,
                    cookies=cookies,
                    callback="parse_list",
                    meta={"page": page_num},
                )
        else:
            url = self._build_list_url()
            if url is None:
                return
            yield Request(
                url=url,
                method=method,
                headers=headers,
                cookies=cookies,
                callback="parse_list",
            )
    
    def parse(self, response: Response) -> Generator[Union[Request, Item], None, None]:
        """Parse the response and yield items or new requests.
        
        Args:
            response (Response): The HTTP response to parse.
            
        Yields:
            Union[Request, Item]: New requests to follow or items to collect.
        """
        yield from self.parse_list(response)
        
    def parse_list(self, response: Response) -> Generator[Union[Request, Item], None, None]:
        """Parse a list page and yield article requests or items."""
        if not response.ok:
            logger.warning(f"List page returned non-OK status {response.status_code}: {response.url}")
            return

        cfg = self._select_list_cfg()
        list_type = cfg.get("type", "html")
        selectors = cfg.get("selectors", {})
        headers = self._request_cfg.get("headers", {})
        cookies = self._request_cfg.get("cookies", {})
        
        if list_type == "json":
            yield from self._parse_json_list(response, selectors, headers, cookies)
        else:
            yield from self._parse_html_list(response, selectors, headers, cookies)
            
    def _parse_html_list(
        self, 
        response: Response, 
        selectors: Dict[str, Any], 
        headers: dict, 
        cookies: dict
    ) -> Generator[Union[Request, Item], None, None]:
        """Parse an HTML list page and yield article requests or items."""
        
        parser = HTMLParser(response.text)
        
        items_selector = selectors.get("items", "a")
        link_selector = selectors.get("link", "a")
        link_attr = selectors.get("link_attr", "href")
        
        for item_elem in parser.select(items_selector):
            link_elem = item_elem.select_one(link_selector) if link_selector != items_selector else item_elem
            if not link_elem:
                continue
            
            href = link_elem.get(link_attr, "") if link_attr != "text" else link_elem.get_text(strip=True)
            if not href:
                continue
            
            url = urljoin(self.base_url, href)
            
            if self._article_cfg:
                yield Request(
                    url=url, 
                    headers=headers, 
                    cookies=cookies, 
                    callback="parse_article", 
                    meta={"list_url": response.url}
                )
            else:
                yield Item(
                    data={"url": url},
                    source=self.name,
                    url=url,
                    item_type="link",
                )
                
    def _parse_json_list(
        self,
        response: Response,
        selectors: Dict[str, Any],
        headers: Dict,
        cookies: Dict,
    ) -> Generator[Union[Item, Request], None, None]:
        """Parse a JSON list response and yield article requests or items."""
        parser = JSONParser(response.text)

        items_path = selectors.get("items", "")
        url_field = selectors.get("url_field", "url")
        url_template = selectors.get("url_template", "{url}")

        items = parser.extract_path(items_path) if items_path else parser.data
        if not isinstance(items, list):
            items = [items]

        for item_data in items:
            raw_url = item_data.get(url_field, "") if isinstance(item_data, dict) else ""
            if not raw_url:
                logger.warning(f"URL field '{url_field}' not found in item data: {item_data}")
                continue
            
            if url_template:
                url = url_template.format(url=raw_url)
            else:
                url = urljoin(self.base_url, raw_url) if raw_url else None

            if self._article_cfg:
                yield Request(
                    url=url,
                    headers=headers,
                    cookies=cookies,
                    callback="parse_article",
                    meta={"list_data": item_data, "list_url": response.url},
                )
            else:
                yield Item(
                    data=item_data if isinstance(item_data, dict) else {"value": item_data},
                    source=self.name,
                    url=url,
                )
                
    def parse_article(
        self, response: Response
    ) -> Generator[Union[Item, Request], None, None]:
        """Parse an article page and yield an item with the extracted data."""
        if not response.ok:
            logger.warning(f"Article page returned non-OK status {response.status_code}: {response.url}")
            return

        article_type = self._article_cfg.get("type", "html")
        selectors = self._article_cfg.get("selectors", {})

        if article_type == "json":
            data = self._extract_article_json(response, selectors)
        else:
            data = self._extract_article_html(response, selectors)

        data.setdefault("url", response.url)

        categories, normalized_categories, tags = self._classifier.classify(response, data)
        if categories:
            data["category"] = categories
        if normalized_categories:
            data["normalized_category"] = normalized_categories
        if tags:
            data["tags"] = tags

        yield Item(
            data=data,
            source=self.name,
            url=response.url,
            item_type="article",
        )
        

    def _extract_article_html(
        self, response: Response, selectors: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract fields from an HTML article page using the provided selectors."""
        parser = HTMLParser(response.text)
        data: Dict[str, Any] = {}

        for field_name, field_cfg in selectors.items():
            if isinstance(field_cfg, str):
                value = parser.extract_text(field_cfg)
            elif isinstance(field_cfg, dict):
                selector = field_cfg.get("selector", "")
                if not selector:
                    logger.warning(f"Field '{field_name}' is missing a selector, skipping.")
                    continue
                attr = field_cfg.get("attr", "text")
                value = parser.extract(selector, attr)
                
                value = self._extract_field(value, field_cfg)
            else:
                continue

            if value is not None:
                data[field_name] = value

        return data

    def _extract_article_json(
        self, response: Response, selectors: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract fields from a JSON article page using the provided selectors."""
        parser = JSONParser(response.text)
        data: Dict[str, Any] = {}

        for field_name, field_cfg in selectors.items():
            if isinstance(field_cfg, str):
                value = parser.extract_path(field_cfg)
            elif isinstance(field_cfg, dict):
                path = field_cfg.get("path", "")
                value = parser.extract_path(path)
                
                value = self._extract_field(value, field_cfg)
            else:
                continue

            if value is not None:
                data[field_name] = value

        return data
        
    def _extract_field(self, value: str, field_cfg: Union[str, Dict[str, Any]]) -> Any:
        """Extract a field value based on the configuration."""
        try:
            if isinstance(field_cfg, dict):
                field_type = field_cfg.get("type")
                
                if field_type == "datetime":
                    date_format = field_cfg.get("datetime_format")
                    if date_format:
                        return datetime.strptime(value, date_format)
                    else:
                        return datetime.fromisoformat(value)            
                elif field_type == "text":
                    regex = field_cfg.get("regex")
                    if regex:
                        match = re.search(regex, value)
                        value = "/".join(match.groups()) if match else value
                    return value.strip()
                
            return value
        except Exception as e:
            logger.warning(f"Failed to extract field with value '{value}' and config '{field_cfg}': {e}")
            return value
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Generator, Union, Any, Dict, Optional
from urllib.parse import urljoin

from ..core import Item, Request, Response
from ..parsers import HTMLParser, JSONParser

from .base import BaseCrawler

logger = logging.getLogger(__name__)

class SiteCrawler(BaseCrawler):
    def __init__(self, site_config: Dict[str, Any]):
        self._config = site_config
        self.name = site_config.get("name", "unknown")
        self.base_url = site_config.get("base_url", "")
        self._list_cfg = site_config.get("list_page", {})
        self._article_cfg = site_config.get("article_page", {})
        self._request_cfg = site_config.get("request", {})
        self._limits = site_config.get("limits", {})

    @property
    def limits(self) -> dict:
        """Site-level crawl limits from the configuration."""
        return self._limits
        
    def start_requests(self) -> Generator[Request, None, None]:
        """Generate initial requests to start crawling the site."""
        list_url = self._list_cfg.get("url", self.base_url)
        pagination = self._list_cfg.get("pagination", {})
        
        headers = self._request_cfg.get("headers", {})
        cookies = self._request_cfg.get("cookies", {})
        
        if pagination.get("enabled", False):
            start = pagination.get("start", 1)
            max_pages = pagination.get("max_pages", 1)

            limits_max_pages = self._limits.get("max_pages")
            if limits_max_pages is not None:
                max_pages = min(max_pages, limits_max_pages)

            for page_num in range(start, start + max_pages):
                url = list_url.format(page=page_num)
                yield Request(
                    url=url, 
                    headers=headers, 
                    cookies=cookies, 
                    callback="parse_list",
                    meta={"page": page_num}, 
                )
        else:
            yield Request(
                url=list_url, 
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

        list_type = self._list_cfg.get("type", "html")
        selectors = self._list_cfg.get("selectors", {})
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
                selectors = field_cfg.get("selector", {})
                attr = field_cfg.get("attr", "text")
                value = parser.extract(selectors, attr)
                
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
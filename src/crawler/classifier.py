from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..parsers import HTMLParser, JSONParser

logger = logging.getLogger(__name__)


class Classifier:
    """Classifies articles into categories and tags based on site config.

    The config declares sources; category sources accumulate all non-empty
    values (deduplicated), and tag sources accumulate values too. Every
    category value is then normalized through an optional global mapping to
    produce the ``normalized_category`` list.

    Supported source types (``source`` field):
        url:     extract a value from the article URL using a regex; ``split`` to divide.
        html:    extract from article HTML via CSS selector; ``attr``/``multiple``/``join``/``split``.
        json:    extract from a JSON data source (``from``: json_ld | list_data | article_json) via ``path``; ``split`` to divide.
        keyword: match keywords in title/content and return rule values.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        category_normalization: Optional[Dict[str, str]] = None,
    ):
        self._config = config
        self._category_cfg = config.get("category") or {}
        self._tags_cfg = config.get("tags") or {}
        self._normalization = category_normalization or {}

    def classify(
        self, response: Any, data: Dict[str, Any]
    ) -> Tuple[List[str], List[str], List[str]]:
        """Return a (categories, normalized_categories, tags) tuple."""
        categories = self._resolve_categories(response, data)
        normalized = self._normalize(categories)
        tags = self._resolve_tags(response, data)
        return categories, normalized, tags

    def _resolve_categories(self, response: Any, data: Dict[str, Any]) -> List[str]:
        categories: List[str] = []
        for source in self._category_cfg.get("sources", []):
            value = self._extract_source(response, data, source)
            if value is None:
                continue
            if source.get("split") and isinstance(value, str):
                values = [v.strip() for v in value.split(source["split"]) if v.strip()]
            elif isinstance(value, list):
                values = [str(v).strip() for v in value if v]
            else:
                values = [str(value).strip()] if str(value).strip() else []
            values = self._apply_mapping(values, source)
            categories.extend(values)
        categories = self._dedupe(categories)
        if not categories and self._category_cfg.get("default"):
            categories = [str(self._category_cfg["default"]).strip()]
        return categories

    def _normalize(self, categories: List[str]) -> List[str]:
        result: List[str] = []
        for value in categories:
            normalized = self._normalization.get(value, value)
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    def _dedupe(self, values: List[str]) -> List[str]:
        seen: set = set()
        result: List[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    def _resolve_tags(self, response: Any, data: Dict[str, Any]) -> List[str]:
        tags: List[str] = []
        for source in self._tags_cfg.get("sources", []):
            value = self._extract_source(response, data, source)
            if value is None:
                continue
            if source.get("split") and isinstance(value, str):
                values = [v.strip() for v in value.split(source["split"]) if v.strip()]
            elif isinstance(value, list):
                values = [str(v).strip() for v in value if v]
            else:
                values = [str(value).strip()] if str(value).strip() else []
            values = self._apply_mapping(values, source)
            tags.extend(values)
        return self._dedupe(tags)

    def _extract_source(
        self, response: Any, data: Dict[str, Any], source: Dict[str, Any]
    ) -> Any:
        stype = source.get("source")
        handler = getattr(self, f"_extract_{stype}", None)
        if not handler:
            logger.warning(f"Unknown classifier source type: {stype}")
            return None
        try:
            return handler(response, data, source)
        except Exception as e:
            logger.warning(f"Classifier source '{stype}' failed: {e}")
            return None

    def _extract_url(self, response: Any, data: Dict[str, Any], source: Dict[str, Any]) -> Optional[str]:
        pattern = source.get("regex")
        if not pattern:
            return None
        match = re.search(pattern, response.url)
        if not match:
            return None
        return match.group(1) if match.groups() else match.group(0)

    def _extract_html(self, response: Any, data: Dict[str, Any], source: Dict[str, Any]) -> Any:
        selector = source.get("selector")
        if not selector:
            return None
        parser = HTMLParser(response.text)
        attr = source.get("attr", "text")
        join = source.get("join")
        multiple = source.get("multiple")
        if join is not None and multiple:
            logger.warning("Classifier html source has both 'join' and 'multiple'; 'join' takes precedence.")
        if join is not None:
            values = []
            for el in parser.select(selector):
                value = el.get_text(strip=True) if attr == "text" else el.get(attr)
                if value:
                    values.append(str(value).strip())
            return join.join(values) if values else None
        if multiple:
            values = []
            for el in parser.select(selector):
                value = el.get_text(strip=True) if attr == "text" else el.get(attr)
                if value:
                    values.append(str(value).strip())
            return values if values else None
        return parser.extract(selector, attr)

    def _extract_json(self, response: Any, data: Dict[str, Any], source: Dict[str, Any]) -> Any:
        from_ = source.get("from")
        path = source.get("path")
        if from_ == "json_ld":
            parser = HTMLParser(response.text)
            for script in parser.select('script[type="application/ld+json"]'):
                raw = script.get_text(strip=True).strip("<!--").strip("-->")
                try:
                    ld_data = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    continue
                value = JSONParser(ld_data).extract_path(path) if path else ld_data
                if value:
                    return value
            return None
        elif from_ == "list_data":
            meta = response.meta or {}
            list_data = meta.get("list_data")
            if list_data is None:
                return None
            if path:
                return JSONParser(list_data).extract_path(path)
            return list_data
        elif from_ == "article_json":
            parser = JSONParser(response.text)
            return parser.extract_path(path) if path else parser.data
        else:
            logger.warning(f"Unknown json source 'from': {from_}")
            return None

    def _extract_keyword(self, response: Any, data: Dict[str, Any], source: Dict[str, Any]) -> List[Optional[str]]:
        text = " ".join(str(data.get(k, "") or "") for k in ("title", "content"))
        result: List[Optional[str]] = []
        for rule in source.get("rules", []):
            keywords = rule.get("keywords", [])
            if any(kw in text for kw in keywords):
                result.append(rule.get("value"))
        return result

    def _apply_mapping(self, value: Any, source: Dict[str, Any]) -> Any:
        mapping = source.get("mapping") or {}
        if not mapping or value is None:
            return value
        if isinstance(value, list):
            return [mapping.get(v, v) for v in value]
        return mapping.get(value, value)

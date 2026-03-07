from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set, Union

import requests
import aiohttp
import httpx

from .request import Request
from .response import Response
from .item import Item

from ..crawler import BaseCrawler
from ..storage import BaseStorage, JSONStorage, DatabaseStorage
from ..utils.config import Settings

logger = logging.getLogger(__name__)


class CrawlerEngine:
    """The core engine that runs the crawling process."""
    def __init__(self, settings: Dict[str, Any]):
        """Initialize the crawler engine with the given settings.
        
        Args:
            settings (Dict[str, Any]): A dictionary of engine configuration settings.
        """
        self.settings = settings or Settings()
        self.storages: List[BaseStorage] = []
        
        # engine configuration
        engine_cfg = self.settings.get("engine", {})
        self._mode = engine_cfg.get("mode", "sync")
        self._max_concurrency = engine_cfg.get("max_concurrency", 10)
        self._request_timeout = engine_cfg.get("request_timeout", 30)
        self._download_delay = engine_cfg.get("download_delay", 1.0)
        self._max_retries = engine_cfg.get("max_retries", 3)
        
    def add_storage(self, storage: BaseStorage) -> CrawlerEngine:
        """Add a storage backend to the engine.
        
        Args:
            storage (BaseStorage): An instance of a storage backend to add.
            
        Returns:
            CrawlerEngine: The engine instance (for chaining).
        """
        self.storages.append(storage)
        logger.debug(f"Added storage backend: {storage.__class__.__name__}")
        return self
        
    def run(self, crawler: BaseCrawler) -> List[Item]:
        """Run the crawler and return the collected items.
        
        Args:
            crawler (BaseCrawler): An instance of a crawler to run.
            
        Returns:
            List[Item]: A list of collected items.
        """
        logger.info(f"Starting crawler: {crawler.name} in {self._mode} mode")
        try:
            if self._mode == "async":
                return asyncio.run(self._run_async(crawler))
            elif self._mode == "sync":
                return self._run_sync(crawler)
            else:
                raise ValueError(f"Invalid engine mode: {self._mode}")
        finally:
            self.close()
            logger.info(f"Crawler finished: {crawler.name}")
            
    def _run_sync(self, crawler: BaseCrawler) -> List[Item]:
        """Run the crawler in synchronous mode.
        
        Args:
            crawler (BaseCrawler): An instance of a crawler to run.
            
        Returns:
            List[Item]: A list of collected items.
        """
        items: List[Item] = []
        queue: deque[Request] = deque()
        seen: set = set()
        
        for req in crawler.start_requests():
            queue.append(req)
            
        total_requests = 0
        
        while queue:
            request = queue.popleft()
            
            if request.url in seen:
                continue
            
            seen.add(request.url)
            
            response = self._process_sync(request)
            if response is None:
                continue
            
            total_requests += 1
            
            callback_name = request.callback or "parse"
            callback = getattr(crawler, callback_name, None)
            if callback is None:
                logger.warning(f"No callback method '{callback_name}' found in crawler '{crawler.name}'")
                continue
            
            for result in callback(response):
                if isinstance(result, Request):
                    queue.append(result)
                elif isinstance(result, Item):
                    items.append(result)
                    self._store(result)
                else:
                    logger.warning(f"Unexpected result type: {type(result)} from callback '{callback_name}'")
                    
            if self._download_delay > 0:
                time.sleep(self._download_delay)
        
        logger.info(f"Successfully processed {total_requests} requests.")
        logger.info(f"Total requests made: {total_requests}")
        logger.info(f"Total items collected: {len(items)}")
        return items
        
    def _process_sync(self, request: Request) -> Optional[Response]:
        """Process a single request in synchronous mode with retries.
        
        Args:
            request (Request): The request to process.

        Returns:
            Optional[Response]: The response object if the request was successful, or None if it failed after retries.
        """
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._fetch_sync(request)
            except Exception as e:
                last_exception = e
                logger.warning(f"Request failed (attempt {attempt}/{self._max_retries}): {request.url} - {e}")
                time.sleep(min(2 ** attempt, 10))
        
        logger.error(f"Failed to process request after {self._max_retries} attempts: {request.url}")
        return None
    
    def _fetch_sync(self, request: Request) -> Optional[Response]:
        """Fetch a single request in synchronous mode and return the response.
        
        Args:
            request (Request): The request to fetch.
        Returns:
            Optional[Response]: The response object if the request was successful, or None if it failed.
        """
        with httpx.Client(timeout=self._request_timeout) as client:
            response = client.request(
                method=request.method,
                url=request.url,
                headers=request.headers or None,
                cookies=request.cookies or None,
                params=request.params or None,
                data=request.body,
                json=request.json_body,
                timeout=self._request_timeout,
            )
            
            return Response(
                url=request.url,
                status_code=response.status_code,
                headers=dict(response.headers),
                cookies=dict(response.cookies),
                text=response.text,
                request=request,
                encoding=response.encoding or "utf-8",
            )
            
    def _store(self, item: Item) -> None:
        """Save an item using all configured storage backends."""
        for storage in self.storages:
            try:
                storage.save(item)
            except Exception as e:
                logger.error(f"Failed to save item with {storage.__class__.__name__}: {e}")
            
    def close(self) -> None:
        """Close any resources used by the engine, such as storage backends."""
        for storage in self.storages:
            try:
                storage.close()
            except Exception as e:
                pass
            
        logger.info("Crawler engine resources have been cleaned up.")

def build_engine(settings: Settings) -> CrawlerEngine:
    engine = CrawlerEngine(settings)
    
    # Storage
    json_cfg = settings.get("json_storage", {})
    if json_cfg.get("enabled", False):
        engine.add_storage(JSONStorage(
            output_dir=json_cfg.get("output_dir", "data/json"),
        ))
        
    db_cfg = settings.get("database", {})
    if db_cfg.get("enabled", False):
        engine.add_storage(DatabaseStorage(
            db_url=db_cfg.get("url", "sqlite:///data/articles.db"),
            echo=db_cfg.get("echo", False),
            pool_size=db_cfg.get("pool_size", 5),
            max_overflow=db_cfg.get("max_overflow", 10),
        ))

    return engine
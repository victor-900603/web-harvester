from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Union

import requests
import aiohttp
import httpx

from .request import Request
from .response import Response
from .item import Item

from ..storage import BaseStorage, JSONStorage, DatabaseStorage
from ..utils.config import Settings

if TYPE_CHECKING:
    from ..crawler import BaseCrawler

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

        # global request configuration
        request_cfg = self.settings.get("request", {})
        self._user_agent = request_cfg.get("user_agent", "web-harvester/1.0")
        self._verify_ssl = request_cfg.get("verify_ssl", True)
        
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
            limits = getattr(crawler, "limits", {}) or {}
            max_items = limits.get("max_items")
            stop_on_duplicate = limits.get("stop_on_duplicate", False)
            timeout = limits.get("timeout")

            if self._mode == "async":
                return asyncio.run(self._run_async(crawler, max_items=max_items, stop_on_duplicate=stop_on_duplicate, timeout=timeout))
            elif self._mode == "sync":
                return self._run_sync(crawler, max_items=max_items, stop_on_duplicate=stop_on_duplicate, timeout=timeout)
            else:
                raise ValueError(f"Invalid engine mode: {self._mode}")
        finally:
            self.close()
            logger.info(f"Crawler finished: {crawler.name}")
            
    def _run_sync(
        self,
        crawler: BaseCrawler,
        max_items: Optional[int] = None,
        stop_on_duplicate: bool = False,
        timeout: Optional[float] = None,
    ) -> List[Item]:
        """Run the crawler in synchronous mode.

        Args:
            crawler (BaseCrawler): An instance of a crawler to run.
            max_items (Optional[int]): Maximum number of items to collect.
            stop_on_duplicate (bool): Stop crawling when a duplicate URL is encountered.
            timeout (Optional[float]): Overall crawl timeout in seconds.

        Returns:
            List[Item]: A list of collected items.
        """
        items: List[Item] = []
        queue: deque[Request] = deque()
        seen: set = set()

        for req in crawler.start_requests():
            queue.append(req)

        total_requests = 0
        start_time = time.time()

        while queue:
            if max_items is not None and len(items) >= max_items:
                logger.info(f"Reached max_items limit of {max_items}. Stopping.")
                break

            if timeout is not None and (time.time() - start_time) > timeout:
                logger.warning(f"Crawl timeout of {timeout}s reached. Stopping.")
                break

            request = queue.popleft()

            if request.url in seen:
                if stop_on_duplicate:
                    logger.info(f"Duplicate URL detected: {request.url}. Stopping.")
                    break
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
        with httpx.Client(
            timeout=self._request_timeout,
            verify=self._verify_ssl,
            headers={"User-Agent": self._user_agent},
        ) as client:
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
            response.raise_for_status()

            return Response(
                url=request.url,
                status_code=response.status_code,
                headers=dict(response.headers),
                cookies=dict(response.cookies),
                text=response.text,
                request=request,
                encoding=response.encoding or "utf-8",
            )

    async def _run_async(
        self,
        crawler: BaseCrawler,
        max_items: Optional[int] = None,
        stop_on_duplicate: bool = False,
        timeout: Optional[float] = None,
    ) -> List[Item]:
        items: List[Item] = []
        queue: asyncio.Queue[Request] = asyncio.Queue()
        seen: set = set()
        semaphore = asyncio.Semaphore(self._max_concurrency)

        for req in crawler.start_requests():
            await queue.put(req)

        total_requests = 0
        start_time = time.time()
        stop_event = asyncio.Event()

        limits = httpx.Limits(max_connections=self._max_concurrency, max_keepalive_connections=self._max_concurrency)
        timeout_cfg = httpx.Timeout(self._request_timeout)

        async with httpx.AsyncClient(
            timeout=timeout_cfg,
            limits=limits,
            verify=self._verify_ssl,
            headers={"User-Agent": self._user_agent},
        ) as client:
            async def drain() -> None:
                while not queue.empty():
                    try:
                        queue.get_nowait()
                        queue.task_done()
                    except asyncio.QueueEmpty:
                        break

            async def worker():
                nonlocal total_requests
                while True:
                    if stop_event.is_set():
                        await drain()
                        break

                    request = await queue.get()  # cancelled here → no item taken, no task_done needed
                    try:
                        if stop_event.is_set():
                            continue

                        if request.url in seen:
                            if stop_on_duplicate:
                                logger.info(f"Duplicate URL detected: {request.url}. Stopping.")
                                stop_event.set()
                            continue

                        seen.add(request.url)
                        response = await self._process_async(client, request)

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
                                await queue.put(result)
                            elif isinstance(result, Item):
                                items.append(result)
                                await self._store_async(result)
                                if max_items is not None and len(items) >= max_items:
                                    logger.info(f"Reached max_items limit of {max_items}. Stopping.")
                                    stop_event.set()
                            else:
                                logger.warning(f"Unexpected result type: {type(result)} from callback '{callback_name}'")

                        if timeout is not None and (time.time() - start_time) > timeout:
                            logger.warning(f"Crawl timeout of {timeout}s reached. Stopping.")
                            stop_event.set()

                        if self._download_delay > 0:
                            await asyncio.sleep(self._download_delay)

                    finally:
                        queue.task_done()

            workers = [asyncio.create_task(worker()) for _ in range(self._max_concurrency)]
            await queue.join()
            for w in workers:
                w.cancel()

        logger.info(f"Successfully processed {total_requests} requests.")
        logger.info(f"Total requests made: {total_requests}")
        logger.info(f"Total items collected: {len(items)}")
        return items
    
    async def _process_async(self, client: httpx.AsyncClient, request: Request) -> Optional[Response]:
        for attempt in range(1, self._max_retries + 1):
            try:
                return await self._fetch_async(client, request)
            except Exception as e:
                last_exception = e
                logger.warning(f"Request failed (attempt {attempt}/{self._max_retries}): {request.url} - {e}")
                await asyncio.sleep(min(2 ** attempt, 10))
        
        logger.error(f"Failed to process request after {self._max_retries} attempts: {request.url}")
        return None
    
    async def _fetch_async(self, client: httpx.AsyncClient, request: Request) -> Optional[Response]:
        response = await client.request(
            method=request.method,
            url=request.url,
            headers=request.headers or None,
            cookies=request.cookies or None,
            params=request.params or None,
            data=request.body,
            json=request.json_body,
        )
        response.raise_for_status()

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

    async def _store_async(self, item: Item) -> None:
        """Save an item asynchronously by running the synchronous _store in a thread pool,
        so the event loop is not blocked by I/O-bound storage operations."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._store, item)
            
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
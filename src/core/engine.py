from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..storage import BaseStorage, DatabaseStorage, JSONStorage
from ..utils.config import Settings
from .http_client import BaseHttpClient, build_http_client
from .item import Item
from .request import Request
from .response import Response
from .retry import BackoffPolicy, is_retryable
from .robots import RobotsPolicy

if TYPE_CHECKING:
    from ..crawler import BaseCrawler

logger = logging.getLogger(__name__)


def _request_key(request: Request) -> tuple:
    """Return a deduplication key that also covers the request body.

    Two list-page requests may share the same URL while differing only in their
    POST body (e.g. offset/cursor pagination). Keying deduplication on the URL
    alone would wrongly drop every page after the first.
    """
    json_body = request.json_body
    json_key = json.dumps(json_body, sort_keys=True) if json_body is not None else None
    return (request.method or "GET", request.url, request.body, json_key)


class CrawlerEngine:
    """The core engine that runs the crawling process."""
    def __init__(self, settings: Dict[str, Any] | Settings, *, skip_seen_urls: Optional[bool] = None):
        """Initialize the crawler engine with the given settings.

        Args:
            settings (Dict[str, Any] | Settings): A dictionary of engine configuration settings.
            skip_seen_urls (Optional[bool]): Override for ``engine.skip_seen_urls``
                (the CLI ``--skip-seen`` flag); None keeps the configured value.
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
        self._retry_policy = BackoffPolicy.from_settings(engine_cfg.get("retry"))

        # global request configuration
        request_cfg = self.settings.get("request", {})
        self._user_agent = request_cfg.get("user_agent", "web-harvester/1.0")
        self._verify_ssl = request_cfg.get("verify_ssl", True)
        self._respect_robots = request_cfg.get("respect_robots", True)

        # HTTP client with TLS fingerprint support (curl_cffi by default)
        self._http_client: BaseHttpClient = build_http_client(self.settings)

        # robots.txt enforcement and cross-run deduplication
        self._skip_seen_urls = (
            engine_cfg.get("skip_seen_urls", True) if skip_seen_urls is None else skip_seen_urls
        )
        self._robots = RobotsPolicy(self._http_client, self._user_agent)
        self._robots_enabled = self._respect_robots
        self._known_urls: set[str] = set()
        self._skipped_known = 0
        self._skipped_robots = 0

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
        self._skipped_known = 0
        self._skipped_robots = 0
        self._robots_enabled = self._resolve_respect_robots(crawler)
        self._known_urls = self._load_known_urls() if self._skip_seen_urls else set()
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

    def _resolve_respect_robots(self, crawler: BaseCrawler) -> bool:
        """Return the effective robots.txt policy for a crawler.

        A site config may override the global ``request.respect_robots`` value;
        the override wins when present.
        """
        override = getattr(crawler, "respect_robots", None)
        if override is None:
            return bool(self._respect_robots)
        return bool(override)

    def _load_known_urls(self) -> set[str]:
        """Collect the URLs already stored so repeated runs skip them."""
        known: set[str] = set()
        for storage in self.storages:
            try:
                known |= storage.known_urls()
            except Exception as e:
                logger.warning(
                    f"Failed to load known URLs from {storage.__class__.__name__}: {e}"
                )
        if known:
            logger.info(f"Loaded {len(known)} known URLs; matching requests will be skipped.")
        return known

    def _is_known_url(self, url: str) -> bool:
        return url in self._known_urls

    def _robots_allows(self, url: str) -> bool:
        """Return whether robots.txt permits fetching ``url`` in this run."""
        if not self._robots_enabled:
            return True
        allowed = self._robots.allowed(url)
        if not allowed:
            self._skipped_robots += 1
        return allowed

    async def _robots_allows_async(self, url: str) -> bool:
        """Asynchronous counterpart of :meth:`_robots_allows`."""
        if not self._robots_enabled:
            return True
        allowed = await self._robots.allowed_async(url)
        if not allowed:
            self._skipped_robots += 1
        return allowed

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

            key = _request_key(request)
            if key in seen:
                if stop_on_duplicate:
                    logger.info(f"Duplicate request detected: {request.method or 'GET'} {request.url}. Stopping.")
                    break
                continue

            seen.add(key)

            if self._is_known_url(request.url):
                self._skipped_known += 1
                if stop_on_duplicate:
                    logger.info(f"Known URL detected: {request.url}. Stopping.")
                    break
                logger.debug(f"Skipping known URL: {request.url}")
                continue

            if not self._robots_allows(request.url):
                continue

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

        logger.info(
            f"Total requests made: {total_requests}, total items collected: {len(items)}, "
            f"skipped known URLs: {self._skipped_known}, skipped by robots.txt: {self._skipped_robots}"
        )
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
                if not is_retryable(e):
                    logger.error(f"Non-retryable error for {request.url}: {e}")
                    return None
                if attempt >= self._max_retries:
                    break
                delay = self._retry_policy.delay(attempt, e)
                logger.warning(
                    f"Request failed (attempt {attempt}/{self._max_retries}): {request.url} - {e}. "
                    f"Retrying in {delay:.2f}s"
                )
                time.sleep(delay)

        logger.error(f"Failed to process request after {self._max_retries} attempts: {request.url}")
        return None

    def _fetch_sync(self, request: Request) -> Optional[Response]:
        """Fetch a single request in synchronous mode and return the response.

        Delegates to the configured :class:`BaseHttpClient` (curl_cffi with
        TLS fingerprint impersonation by default, or httpx fallback).

        Args:
            request (Request): The request to fetch.
        Returns:
            Optional[Response]: The response object if the request was successful, or None if it failed.
        """
        return self._http_client.fetch_sync(request)

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

        for req in crawler.start_requests():
            await queue.put(req)

        total_requests = 0
        start_time = time.time()
        stop_event = asyncio.Event()

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

                    key = _request_key(request)
                    if key in seen:
                        if stop_on_duplicate:
                            logger.info(f"Duplicate request detected: {request.method or 'GET'} {request.url}. Stopping.")
                            stop_event.set()
                        continue

                    seen.add(key)

                    if self._is_known_url(request.url):
                        self._skipped_known += 1
                        if stop_on_duplicate:
                            logger.info(f"Known URL detected: {request.url}. Stopping.")
                            stop_event.set()
                            continue
                        logger.debug(f"Skipping known URL: {request.url}")
                        continue

                    if not await self._robots_allows_async(request.url):
                        continue

                    response = await self._process_async(request)

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

        logger.info(
            f"Total requests made: {total_requests}, total items collected: {len(items)}, "
            f"skipped known URLs: {self._skipped_known}, skipped by robots.txt: {self._skipped_robots}"
        )
        return items

    async def _process_async(self, request: Request) -> Optional[Response]:
        """Process async request with retries."""
        for attempt in range(1, self._max_retries + 1):
            try:
                return await self._fetch_async(request)
            except Exception as e:
                if not is_retryable(e):
                    logger.error(f"Non-retryable error for {request.url}: {e}")
                    return None
                if attempt >= self._max_retries:
                    break
                delay = self._retry_policy.delay(attempt, e)
                logger.warning(
                    f"Request failed (attempt {attempt}/{self._max_retries}): {request.url} - {e}. "
                    f"Retrying in {delay:.2f}s"
                )
                await asyncio.sleep(delay)

        logger.error(f"Failed to process request after {self._max_retries} attempts: {request.url}")
        return None

    async def _fetch_async(self, request: Request) -> Optional[Response]:
        """Fetch async request via the configured HTTP client."""
        return await self._http_client.fetch_async(request)

    def _store(self, item: Item) -> None:
        """Save an item using all configured storage backends."""
        for storage in self.storages:
            try:
                storage.save(item)
            except Exception as e:
                logger.error(f"Failed to save item with {storage.__class__.__name__}: {e}", exc_info=True)

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
                logger.debug(f"Failed to close {storage.__class__.__name__}: {e}", exc_info=True)
        try:
            self._http_client.close()
        except Exception as e:
            logger.debug(f"Failed to close HTTP client: {e}", exc_info=True)

        logger.info("Crawler engine resources have been cleaned up.")

def build_engine(settings: Settings, *, skip_seen_urls: Optional[bool] = None) -> CrawlerEngine:
    engine = CrawlerEngine(settings, skip_seen_urls=skip_seen_urls)

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

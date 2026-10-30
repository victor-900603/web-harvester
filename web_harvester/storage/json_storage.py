from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from typing import Any, Dict, List

from ..core.item import Item
from .base import BaseStorage


class _DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that converts datetime/date objects to ISO-8601 strings."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

logger = logging.getLogger(__name__)

class JSONStorage(BaseStorage):
    """Storage backend that saves items to a JSON file.

    Items are grouped by ``Item.source``; every source gets its own file named
    with the template and the timestamp of its first write, so interleaved
    sources never overwrite each other.

    In batch mode records are buffered and written when ``flush_interval`` new
    items have accumulated for that source, and again on :meth:`close`.
    ``flush_interval=0`` keeps everything in memory until ``close``. Each write
    goes through a temporary file and :func:`os.replace`, so an interrupted run
    never leaves a truncated JSON document behind.
    """

    def __init__(
        self,
        output_dir: str = "data/json",
        filename_template: str = "{source}_{date}.json",
        batch_mode: bool = True,
        flush_interval: int = 10,
    ):
        self.output_dir = output_dir
        self.filename_template = filename_template
        self.batch_mode = batch_mode
        self.flush_interval = max(0, int(flush_interval))
        self._records: Dict[str, List[Dict[str, Any]]] = {}
        self._paths: Dict[str, str] = {}
        self._unflushed: Dict[str, int] = {}

        os.makedirs(self.output_dir, exist_ok=True)

    def save(self, item: Item) -> None:
        """Save an item, flushing its source once the interval is reached."""
        source = item.source or "unknown"
        record = item.to_dict()

        if not self.batch_mode:
            filepath = self._filepath_for(source)
            self._append_to_file(filepath, record)
            logger.debug(f"Saved item to {filepath}.")
            return

        self._records.setdefault(source, []).append(record)
        pending = self._unflushed.get(source, 0) + 1
        self._unflushed[source] = pending
        if self.flush_interval and pending >= self.flush_interval:
            self._flush_source(source)

    def save_many(self, items: List[Item]) -> None:
        """Save multiple items using the same batching rules as :meth:`save`."""
        for item in items:
            self.save(item)

    def flush(self) -> None:
        """Write the buffered records of every source to disk."""
        for source in list(self._records):
            if self._unflushed.get(source, 0):
                self._flush_source(source)

    def close(self) -> None:
        """Flush any remaining records."""
        self.flush()

    def _flush_source(self, source: str) -> None:
        records = self._records.get(source) or []
        if not records:
            return

        filepath = self._filepath_for(source)
        self._write_json(filepath, records)
        self._unflushed[source] = 0
        logger.debug(f"Saved {len(records)} items to {filepath}.")

    def _filepath_for(self, source: str) -> str:
        """Return the file path of ``source``, fixed at its first write."""
        filepath = self._paths.get(source)
        if filepath is None:
            filepath = self._get_filepath(source)
            self._paths[source] = filepath
            logger.debug(f"Writing source '{source}' to {filepath}.")
        return filepath

    def _get_filepath(self, source: str) -> str:
        """Generate a file path based on the source and current date.

        Args:
            source (str): The source name to include in the filename.

        Returns:
            str: The generated file path.
        """
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.filename_template.format(source=source, date=date_str)
        return os.path.join(self.output_dir, filename)

    @staticmethod
    def _write_json(filepath: str, data: List[Dict[str, Any]]) -> None:
        """Atomically write a list of dictionaries to a JSON file.

        Args:
            filepath (str): The path to the JSON file.
            data (List[Dict[str, Any]]): The data to write to the file.
        """
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        tmp_path = f"{filepath}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4, cls=_DateTimeEncoder)
        os.replace(tmp_path, filepath)

    @classmethod
    def _append_to_file(cls, filepath: str, data: Dict[str, Any]) -> None:
        """Append a single dictionary to a JSON file, creating the file if it doesn't exist.

        Args:
            filepath (str): The path to the JSON file.
            data (Dict[str, Any]): The data to append to the file.
        """
        existing_data: List[Dict[str, Any]] = []
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = []

        existing_data.append(data)
        cls._write_json(filepath, existing_data)

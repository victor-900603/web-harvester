from __future__ import annotations

import logging
import json
import os
from typing import Any, List, Dict
from datetime import datetime, date

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
    """Storage backend that saves items to a JSON file."""
    
    def __init__(
        self, 
        output_dir: str = "data/json", 
        filename_template: str = "{source}_{date}.json",
        batch_mode: bool = True,
    ):
        self.output_dir = output_dir
        self.filename_template = filename_template
        self.batch_mode = batch_mode
        self._buffer: List[dict] = []
        self._current_source: str = ""
        
        os.makedirs(self.output_dir, exist_ok=True)
        
    def save(self, item: Item) -> None:
        """Save an item to the JSON file."""
        data = item.to_dict()
        
        if self.batch_mode:
            self._buffer.append(data)
            self._current_source = item.source
        else:
            filepath = self._get_filepath(item.source)
            self._append_to_file(filepath, data)
            logger.debug(f"Saved item to {filepath}.")
            
    def save_many(self, items: List[Item]) -> None:
        """Save multiple items to the JSON file."""
        for item in items:
            self._buffer.append(item.to_dict())
            self._current_source = item.source
            
    def close(self) -> None:
        if self._buffer:
            filepath = self._get_filepath(self._current_source)
            self._write_json(filepath, self._buffer)
            logger.debug(f"Saved {len(self._buffer)} items to {filepath}.")
            self._buffer.clear()
            
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
        """Write a list of dictionaries to a JSON file.
        
        Args:
            filepath (str): The path to the JSON file.
            data (List[Dict[str, Any]]): The data to write to the file.
        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4, cls=_DateTimeEncoder)
            
    @staticmethod
    def _append_to_file(filepath: str, data: Dict[str, Any]) -> None:
        """Append a single dictionary to a JSON file, creating the file if it doesn't exist.
        
        Args:
            filepath (str): The path to the JSON file.
            data (Dict[str, Any]): The data to append to the file.
        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        if os.path.exists(filepath):
            with open(filepath, "r+", encoding="utf-8") as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = []
        else:
            existing_data = []

        existing_data.append(data)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4, cls=_DateTimeEncoder)
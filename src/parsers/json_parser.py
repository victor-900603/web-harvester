from __future__ import annotations

from typing import Any, Dict, Optional, Union, List
import json

class JSONParser:
    """A JSON parser that can handle both JSON strings and already parsed JSON data.
    
    Args:
        content (str | Dict[str, Any] | List[Any]): The JSON content to parse, either as a string or as a pre-parsed dictionary/list.
        
    Example:
        json_string = '{"name": "Alice", "age": 30, "hobbies": ["reading", "hiking"]}'
        parser = JSONParser(json_string)
        print(parser.data)  # Output: {'name': 'Alice', 'age': 30, 'hobbies': ['reading', 'hiking']}
    """
    def __init__(self, content: str | Dict[str, Any] | List[Any]) -> None:
        if isinstance(content, str):
            self.data = json.loads(content)
        else:
            self.data = content
            
    def extract_path(self, path: str) -> Optional[Any]:
        """Extract a value from the JSON data using a dot-separated path.
        
        Args:
            path (str): The dot-separated path to the desired value (e.g., "user.name" or "items.0.title").
            
        Returns:
            Optional[Any]: The extracted value, or None if the path does not exist.
        """
        keys = path.split(".")
        current = self.data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and key.isdigit() and 0 <= int(key) < len(current):
                current = current[int(key)]
            else:
                return None
        return current

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from datetime import datetime, timezone


@dataclass
class Item:
    """Data item object.

    Attributes:
        data: A dictionary of the item's data fields and their values.

    """
    
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    url: str = ""
    item_type: str = "article"
    crawler_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Converts the Item to a dictionary."""
        return {
            "source": self.source,
            "url": self.url,
            "item_type": self.item_type,
            "crawler_at": self.crawler_at,
            **self.data
        }
        
    def __repr__(self):
        return f"<Item type={self.item_type} url={self.url}>"
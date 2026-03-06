from __future__ import annotations

from abc import ABC, abstractmethod

from ..core import Item

class BaseStorage(ABC):
    """Abstract base class for storage backends."""
    
    @abstractmethod
    def save(self, item: Item) -> None:
        """Save an item to the storage backend.
        
        Args:
            item (Item): The item to save.
        """
        raise NotImplementedError("Storage backends must implement the save method.")
    
    def save_many(self, items: list[Item]) -> None:
        """Save multiple items to the storage backend.
        
        Args:
            items (list[Item]): A list of items to save.
        """
        for item in items:
            self.save(item)
            
    def close(self) -> None:
        """Close any resources used by the storage backend."""
        pass
from __future__ import annotations

import json
import logging
from typing import Optional

from ..core.item import Item
from .base import BaseStorage
from .database import get_session, init_database, close_database, Session as DBSession
from .models import Article

logger = logging.getLogger(__name__)

class DatabaseStorage(BaseStorage):
    """Storage backend that saves items to a relational database using SQLAlchemy."""
    
    def __init__(
        self, 
        db_url: str = "sqlite:///data/articles.db", 
        echo: bool = False,
        **kwargs,
    ):
        init_database(db_url, echo=echo, **kwargs)
        self._known_fields = {
            "title", "content", "author", "published_at",
            "category", "tags", "url",
        }
        
    def save(self, item: Item) -> None:
        """Save an item to the database."""
        session = get_session()
        
        try:
            self._store(item, session)
            
            session.commit()
            logger.debug(f"Saved item to database: {item.data.get('title', item.url)}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save item to database: {e}")
            raise
        finally:
            session.close()
            
    def save_many(self, items: list[Item]) -> None:
        """Save multiple items to the database."""
        session = get_session()
        try:
            for item in items:
                self._store(item, session)
            
            session.commit()
            logger.debug(f"Saved {len(items)} items to database.")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save items to database: {e}")
            raise
        finally:
            session.close()
            
    def _store(self, item: Item, session: DBSession) -> None:
        data = item.data
        url = data.get("url", item.url)
        
        if url:
            existing = session.query(Article).filter_by(url=url).first()
            if existing:
                logger.debug(f"Item with URL already exists in database: {url}")
                return
            
        extra_data = {k: v for k, v in data.items() if k not in self._known_fields}
        
        article = Article(
            source=item.source,
            url=item.url,
            
            title=data.get("title", ""),
            author=data.get("author"),
            published_at=data.get("published_at"),
            content=data.get("content", ""),
            category=data.get("category"),
            tags=data.get("tags"),
            item_type=item.item_type,
            extra_data=json.dumps(extra_data) if extra_data else None,
        )
        session.add(article)
                
    def close(self) -> None:
        """Close any resources used by the storage backend."""
        close_database()
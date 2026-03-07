from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

logger = logging.getLogger(__name__)

_SESSION_FACTORY: Optional[sessionmaker] = None
_engine = None

def init_database(
    db_url: str = "sqlite:///data/articles.db", 
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> None:
    """Initialize the database engine and session factory."""
    global _SESSION_FACTORY, _engine

    connect_args = {}
    kwargs = {'echo': echo}
    
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        kwargs["pool_size"] = pool_size
        kwargs["max_overflow"] = max_overflow
    
    _engine = sa_create_engine(db_url, connect_args=connect_args, **kwargs)
    _SESSION_FACTORY = sessionmaker(bind=_engine)
    
    Base.metadata.create_all(_engine)
    logger.info(f"Database engine initialized with URL: {db_url}")
    
def get_session() -> Session:
    """Get a new database session."""
    if _SESSION_FACTORY is None:
        raise RuntimeError("Database engine not initialized. Call init_database() first.")
    return _SESSION_FACTORY()

def close_database() -> None:
    """Close the database engine and session factory."""
    global _SESSION_FACTORY, _engine
    _SESSION_FACTORY = None

    if _engine is not None:
        _engine.dispose()
        _engine = None
        
    logger.info("Database engine and session factory have been closed.")
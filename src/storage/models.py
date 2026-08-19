from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, Index
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass

class Article(Base):
    """Model representing a news article."""
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(255), nullable=False, index=True, comment="The source or website the article was scraped from")
    url = Column(String(2048), nullable=False, unique=True, comment="The URL of the article")
    
    title = Column(String(512), nullable=False, comment="The title of the article")
    author = Column(String(255), comment="The author of the article")
    published_at = Column(DateTime, comment="The publication date and time of the article")
    content = Column(Text, nullable=False, comment="The content of the article")
    category = Column(Text, comment="JSON array of categories of the article")
    normalized_category = Column(Text, comment="JSON array of normalized category names")
    tags = Column(Text, comment="JSON array of tags associated with the article")
    item_type = Column(String(50), nullable=False, comment="The type of item, e.g. 'article'")
    
    crawler_at = Column(
        DateTime, 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc), 
        comment="The date and time when the article was crawled"
    )
    extra_data = Column(Text, comment="Any additional data in JSON format")
    
    __table_args__ = (
        Index("idx_source_publication_date", "source", "published_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Article(id={self.id}, source='{self.source}', title='{self.title}')>"
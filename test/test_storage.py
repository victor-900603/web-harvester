from __future__ import annotations

import json as json_lib
from datetime import datetime, timezone

import pytest

from src.core import Item
from src.storage.json_storage import JSONStorage
from src.storage.db_storage import DatabaseStorage
from src.storage.database import get_session, close_database
from src.storage.models import Article
from conftest import make_item


class TestJSONStorage:
    def test_batch_mode_writes_on_close(self, tmp_path):
        storage = JSONStorage(output_dir=str(tmp_path), batch_mode=True)
        storage.save(make_item(url="https://example.com/1", title="A"))
        storage.save(make_item(url="https://example.com/2", title="B"))
        storage.close()

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        data = json_lib.loads(files[0].read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["title"] == "A"
        assert data[0]["source"] == "example"

    def test_batch_mode_no_write_without_close(self, tmp_path):
        storage = JSONStorage(output_dir=str(tmp_path), batch_mode=True)
        storage.save(make_item(url="https://example.com/1"))
        assert list(tmp_path.iterdir()) == []

    def test_close_without_items_no_file(self, tmp_path):
        storage = JSONStorage(output_dir=str(tmp_path), batch_mode=True)
        storage.close()
        assert list(tmp_path.iterdir()) == []

    def test_save_many(self, tmp_path):
        storage = JSONStorage(output_dir=str(tmp_path), batch_mode=True)
        storage.save_many(
            [
                make_item(url="https://example.com/1"),
                make_item(url="https://example.com/2"),
            ]
        )
        storage.close()
        data = json_lib.loads(next(tmp_path.iterdir()).read_text(encoding="utf-8"))
        assert len(data) == 2

    def test_datetime_serialized_to_iso(self, tmp_path):
        storage = JSONStorage(output_dir=str(tmp_path), batch_mode=True)
        item = make_item(url="https://example.com/1")
        item.crawler_at = datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)
        storage.save(item)
        storage.close()
        data = json_lib.loads(next(tmp_path.iterdir()).read_text(encoding="utf-8"))
        assert data[0]["crawler_at"] == "2026-08-19T10:00:00+00:00"

    @pytest.mark.xfail(reason="既有 bug: _append_to_file 在檔案不存在時 reference before assignment", strict=True)
    def test_non_batch_mode_first_save(self, tmp_path):
        storage = JSONStorage(output_dir=str(tmp_path), batch_mode=False)
        storage.save(make_item(url="https://example.com/1"))
        storage.close()


class TestDatabaseStorage:
    def test_save_and_query(self, tmp_path):
        db_url = f"sqlite:///{tmp_path}/test.db"
        storage = DatabaseStorage(db_url=db_url)
        storage.save(make_item(url="https://example.com/1", title="Hello", category="news"))

        session = get_session()
        try:
            articles = session.query(Article).all()
            assert len(articles) == 1
            assert articles[0].title == "Hello"
            assert articles[0].category == "news"
            assert articles[0].source == "example"
        finally:
            session.close()
            storage.close()
            close_database()

    def test_duplicate_url_skipped(self, tmp_path):
        db_url = f"sqlite:///{tmp_path}/test.db"
        storage = DatabaseStorage(db_url=db_url)
        storage.save(make_item(url="https://example.com/1"))
        storage.save(make_item(url="https://example.com/1"))

        session = get_session()
        try:
            assert session.query(Article).count() == 1
        finally:
            session.close()
            storage.close()
            close_database()

    def test_extra_data_serialized(self, tmp_path):
        db_url = f"sqlite:///{tmp_path}/test.db"
        storage = DatabaseStorage(db_url=db_url)
        storage.save(make_item(url="https://example.com/1", custom_field="xyz"))

        session = get_session()
        try:
            article = session.query(Article).one()
            assert json_lib.loads(article.extra_data) == {"custom_field": "xyz"}
        finally:
            session.close()
            storage.close()
            close_database()

    def test_save_many(self, tmp_path):
        db_url = f"sqlite:///{tmp_path}/test.db"
        storage = DatabaseStorage(db_url=db_url)
        storage.save_many(
            [
                make_item(url="https://example.com/1"),
                make_item(url="https://example.com/2"),
            ]
        )

        session = get_session()
        try:
            assert session.query(Article).count() == 2
        finally:
            session.close()
            storage.close()
            close_database()
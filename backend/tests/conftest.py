"""pytest 共享 fixture：FastAPI TestClient + fixtures 目录路径。"""

import os

# TestClient 每个请求运行在独立事件循环；test 模式下全局 engine 使用
# NullPool，连接随请求生灭，不跨循环复用（须在导入 app 之前设置）。
os.environ.setdefault("APP_ENV", "test")

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import create_app
from tests.support import ensure_schema, pg_url, reset_pg, run


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture()
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def pg_schema():
    ensure_schema(pg_url())
    yield


@pytest.fixture()
def pg_session(pg_schema):
    engine = create_async_engine(pg_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    run(reset_pg(session))
    yield session
    run(session.close())
    run(engine.dispose())

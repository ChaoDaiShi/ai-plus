"""异步 engine 与 session 工厂（asyncpg）。bge-m3 推理端单例装载，不在此建连接。"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# test 模式（多事件循环客户端）用 NullPool；常规 dev/prod 保持连接池。
if settings.app_env == "test":
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(settings.database_url, pool_pre_ping=True, poolclass=NullPool)
else:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with SessionFactory() as session:
        yield session

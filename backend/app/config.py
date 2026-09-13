"""应用配置：全部来自环境变量，默认值仅面向本地开发。"""

import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url

# 开发闭环确定性预置身份（seed_dev 复用此处常量，禁止示例字符串入库）。
TENANT_PRESET_ID = uuid.uuid5(uuid.NAMESPACE_URL, "insightx/dev/tenant-preset")
PROJECT_PRESET_ID = uuid.uuid5(uuid.NAMESPACE_URL, "insightx/dev/project-home")


def sync_db_url(async_url: str) -> str:
    """将 asyncpg 数据库 URL 转为 Alembic 同步驱动（psycopg3），保留全部连接参数。"""
    url = make_url(async_url)
    driver = url.drivername or ""
    if "+asyncpg" in driver:
        url = url.set(drivername=driver.replace("+asyncpg", "+psycopg"))
    elif driver == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+asyncpg://insightx:insightx@localhost:5432/insightx"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:5173"]
    # P0 单企业开发闭环的预置身份；真实身份/项目接入后由服务端会话取代。
    # 值必须为 UUID 字符串；生产模式禁用预置身份（见 app.api.deps）。
    preset_tenant_id: str = str(TENANT_PRESET_ID)
    preset_project_id: str = str(PROJECT_PRESET_ID)
    # P0 数据来源：demo（内置演示数据集）或 http（真实 Amazon 采集 API）。
    # http 模式缺少凭证在节点执行时 fail-fast，禁止自动回退 demo。
    amazon_provider: str = "demo"
    amazon_api_base_url: str = ""
    amazon_api_key: str = ""
    # P0 向量化：deterministic（确定性测试向量）或 bge_m3（需安装 embedding extra）。
    embedding_provider: str = "deterministic"
    # P1 预留：配置 Anthropic Key 后 proposal 命名可切换 LLM，未配置走规则引擎。
    anthropic_api_key: str = ""


settings = Settings()

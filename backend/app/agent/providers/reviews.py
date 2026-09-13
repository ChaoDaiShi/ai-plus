"""评论采集 Provider（任务 §6）：demo 内置数据集与真实 HTTP 采集两个明确模式。

demo 模式读取 app/demo_data/ 下的人工合成数据集，来源标记 DEMO_DATASET，
禁止在任何对外文案中表述为实时抓取；http 模式调用配置的 Amazon 采集 API，
凭证缺失时 fail-fast，禁止自动回退 demo。
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.config import settings

DEMO_DATA_DIR = Path(__file__).resolve().parents[2] / "demo_data"


class ProviderError(Exception):
    """采集失败：可重试性由上层 classify_error 判定（网络类为瞬时）。"""


@dataclass
class RawReview:
    source_review_id: str
    title: str
    text: str
    rating: float | None
    language: str | None
    reviewed_at: date | None
    verified_purchase: bool | None
    helpful_votes: int | None
    source_url: str | None = None


@dataclass
class ReviewFetch:
    """一次采集结果：原始评论与来源元数据（写入 DataSnapshot/ProductSnapshot）。"""

    reviews: list[RawReview]
    source: str
    source_query: dict[str, Any] = field(default_factory=dict)
    product_title: str | None = None
    product_price: float | None = None
    product_currency: str | None = None


class AmazonReviewProvider(Protocol):
    name: str

    async def fetch_reviews(
        self, asin: str, marketplace: str, window_start: date, window_end: date
    ) -> ReviewFetch: ...


class DemoAmazonReviewProvider:
    """读取内置演示数据集；未收录 ASIN 明确报错，不生成假数据。"""

    name = "demo_dataset"

    async def fetch_reviews(
        self, asin: str, marketplace: str, window_start: date, window_end: date
    ) -> ReviewFetch:
        path = DEMO_DATA_DIR / f"{asin}.json"
        if not path.is_file():
            raise ProviderError(
                f"演示数据集未收录 ASIN {asin}；当前仅提供 B08N5WRWNW"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        reviews = []
        for record in payload["reviews"]:
            reviewed_at = date.fromisoformat(record["date"]) if record.get("date") else None
            if reviewed_at is not None and not (window_start <= reviewed_at <= window_end):
                continue  # 时间窗过滤：窗口外评论不进入快照（coverage 据实反映）
            reviews.append(
                RawReview(
                    source_review_id=record["review_id"],
                    title=record.get("title") or "",
                    text=record.get("body") or "",
                    rating=record.get("rating"),
                    language=record.get("language"),
                    reviewed_at=reviewed_at,
                    verified_purchase=record.get("verified_purchase"),
                    helpful_votes=record.get("helpful_votes"),
                )
            )
        product = payload.get("product", {})
        return ReviewFetch(
            reviews=reviews,
            source="demo_dataset",
            source_query={
                "asin": asin,
                "marketplace": marketplace,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "provider": "demo",
            },
            product_title=product.get("title"),
            product_price=product.get("price"),
            product_currency=product.get("currency"),
        )


class HttpAmazonReviewProvider:
    """真实采集模式：调用 AMAZON_API_BASE_URL，未配置凭证 fail-fast。"""

    name = "amazon_http"

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def fetch_reviews(
        self, asin: str, marketplace: str, window_start: date, window_end: date
    ) -> ReviewFetch:
        if not self.base_url or not self.api_key:
            raise ProviderError(
                "AMAZON_PROVIDER=http 需要配置 AMAZON_API_BASE_URL 与 AMAZON_API_KEY，"
                "禁止自动回退演示数据"
            )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.base_url}/reviews",
                    params={
                        "asin": asin,
                        "marketplace": marketplace,
                        "start_date": window_start.isoformat(),
                        "end_date": window_end.isoformat(),
                    },
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                payload = resp.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError("Amazon 采集 API 超时") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Amazon 采集 API 请求失败：{exc}") from exc
        reviews = [
            RawReview(
                source_review_id=item["review_id"],
                title=item.get("title") or "",
                text=item.get("body") or item.get("text") or "",
                rating=item.get("rating"),
                language=item.get("language"),
                reviewed_at=(
                    date.fromisoformat(item["date"]) if item.get("date") else None
                ),
                verified_purchase=item.get("verified_purchase"),
                helpful_votes=item.get("helpful_votes"),
                source_url=item.get("source_url"),
            )
            for item in payload.get("reviews", [])
        ]
        return ReviewFetch(
            reviews=reviews,
            source="amazon_http",
            source_query={
                "asin": asin,
                "marketplace": marketplace,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "provider": "http",
                "base_url": self.base_url,
            },
            product_title=payload.get("product", {}).get("title"),
            product_price=payload.get("product", {}).get("price"),
            product_currency=payload.get("product", {}).get("currency"),
        )


def get_review_provider() -> AmazonReviewProvider:
    """按配置返回采集 Provider；demo 仅限非生产环境（与预置身份同一防线）。"""
    if settings.amazon_provider == "demo":
        if settings.app_env == "prod":
            raise ProviderError("生产环境禁止使用演示数据集（AMAZON_PROVIDER=demo）")
        return DemoAmazonReviewProvider()
    if settings.amazon_provider == "http":
        return HttpAmazonReviewProvider(
            settings.amazon_api_base_url, settings.amazon_api_key
        )
    raise ProviderError(f"未知 AMAZON_PROVIDER：{settings.amazon_provider}")

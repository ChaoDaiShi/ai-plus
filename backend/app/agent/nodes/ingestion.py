"""ingestion 节点：调用采集 Provider，落原始评论、商品快照与数据快照。

来源模式由 AMAZON_PROVIDER 决定（demo / http）；演示数据集来源标记
demo_dataset，报告层据此输出 source_mode=DEMO_DATASET。
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.agent.nodes.common import NodeDataError, content_hash, dump_summary
from app.agent.providers.reviews import get_review_provider
from app.db.models import DataSnapshot, ProductSnapshot, Review, SnapshotReview

CLEANING_VERSION = "norm-v1"


async def run(session_factory, state: dict) -> tuple[dict, dict]:
    tenant_id = uuid.UUID(state["tenant_id"])
    product_id = uuid.UUID(state["product_id"])
    asin = state["asin"]
    marketplace = state["marketplace"]
    window = state["window"]
    window_start = window["start_date"]
    window_end = window["end_date"]

    provider = get_review_provider()
    fetch = await provider.fetch_reviews(
        asin,
        marketplace,
        date.fromisoformat(window_start),
        date.fromisoformat(window_end),
    )

    observed = datetime.now(timezone.utc)
    async with session_factory() as session, session.begin():
        existing = (
            await session.execute(
                select(Review).where(Review.product_id == product_id)
            )
        ).scalars().all()
        by_identity = {
            (r.source_review_id, r.content_hash): r for r in existing
        }

        product_snapshot = ProductSnapshot(
            tenant_id=tenant_id,
            product_id=product_id,
            observed_at=observed,
            source=fetch.source,
            title=fetch.product_title,
            price=fetch.product_price,
            currency=fetch.product_currency,
        )
        session.add(product_snapshot)
        await session.flush()

        snapshot = DataSnapshot(
            tenant_id=tenant_id,
            product_id=product_id,
            product_snapshot_id=product_snapshot.id,
            observed_at=observed,
            source=fetch.source,
            source_query=fetch.source_query,
            cleaning_version=CLEANING_VERSION,
            coverage={},
            content_hash=content_hash(
                "|".join(r.source_review_id for r in fetch.reviews)
            ),
        )
        session.add(snapshot)
        await session.flush()

        review_ids: list[uuid.UUID] = []
        for raw in fetch.reviews:
            text = raw.text or ""
            identity = (raw.source_review_id, content_hash(text))
            review = by_identity.get(identity)
            if review is None:
                review = Review(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    source_review_id=raw.source_review_id,
                    content_hash=identity[1],
                    raw_text=text,
                    rating=raw.rating,
                    language=raw.language,
                    reviewed_at=raw.reviewed_at,
                    observed_at=observed,
                    source_url=raw.source_url,
                )
                session.add(review)
                await session.flush()
                by_identity[identity] = review
            review_ids.append(review.id)
            session.add(
                SnapshotReview(
                    snapshot_id=snapshot.id, review_id=review.id, included=True
                )
            )
        await session.flush()

    summary = {
        "raw_count": len(fetch.reviews),
        "source": fetch.source,
        "source_mode": "DEMO_DATASET" if fetch.source == "demo_dataset" else "LIVE_API",
        "snapshot_id": str(snapshot.id),
        "provider": provider.name,
    }
    updates = {
        "snapshot_id": str(snapshot.id),
        "source": fetch.source,
        "raw_count": len(fetch.reviews),
    }
    return dump_summary(summary), updates


async def recover_snapshot_id(
    session_factory, item_id: uuid.UUID, attempt: int
) -> str | None:
    """恢复路径：从 ingestion 节点 output_summary 取 snapshot_id。"""
    from app.agent.nodes.common import load_node_summary

    async with session_factory() as session:
        summary = await load_node_summary(session, item_id, attempt, "ingestion")
    if summary is None or not summary.get("snapshot_id"):
        raise NodeDataError("ingestion 节点产物缺失，无法恢复 snapshot_id")
    return str(summary["snapshot_id"])

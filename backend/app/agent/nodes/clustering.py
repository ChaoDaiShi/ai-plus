"""clustering 节点：从 DB 加载片段向量执行聚类，簇草稿写入状态与 output_summary。

簇草稿（无 ID）沿状态传给 proposal/publish；publish 落库后才有真实
cluster UUID。恢复路径从本节点 output_summary 重载草稿。
"""

import uuid

from sqlalchemy import select

from app.agent.nodes.common import dump_summary
from app.agent.providers.clustering import (
    CLUSTERING_VERSION,
    ClusterDraft,
    FragmentInput,
    cluster_fragments,
)
from app.db.models import Review, ReviewFragment, SnapshotReview


def draft_to_dict(key: str, draft: ClusterDraft) -> dict:
    return {
        "key": key,
        "name_zh": draft.name_zh,
        "name_en": draft.name_en,
        "category": draft.category,
        "frequency": draft.frequency,
        "denominator": draft.denominator,
        "severity": draft.severity,
        "severity_reason": draft.severity_reason,
        "keywords": draft.keywords,
        "review_ids": draft.review_ids,
        "fragment_ids": draft.fragment_ids,
        "sample_text": draft.sample_text,
        "sample_review_id": draft.sample_review_id,
    }


def dict_to_draft(data: dict) -> ClusterDraft:
    return ClusterDraft(
        name_zh=data["name_zh"],
        name_en=data["name_en"],
        category=data["category"],
        frequency=data["frequency"],
        denominator=data["denominator"],
        severity=data["severity"],
        severity_reason=data["severity_reason"],
        keywords=data["keywords"],
        review_ids=data["review_ids"],
        fragment_ids=data["fragment_ids"],
        sample_text=data.get("sample_text", ""),
        sample_review_id=data.get("sample_review_id", ""),
    )


async def run(session_factory, state: dict) -> tuple[dict, dict]:
    tenant_id = uuid.UUID(state["tenant_id"])
    snapshot_id = uuid.UUID(state["snapshot_id"])

    async with session_factory() as session:
        reviews = (
            await session.execute(
                select(Review)
                .join(SnapshotReview, SnapshotReview.review_id == Review.id)
                .where(
                    SnapshotReview.snapshot_id == snapshot_id,
                    SnapshotReview.included.is_(True),
                    Review.rating <= 3.0,
                )
                .order_by(Review.id)
            )
        ).scalars().all()
        fragments = (
            await session.execute(
                select(ReviewFragment)
                .where(
                    ReviewFragment.review_id.in_([r.id for r in reviews]),
                    ReviewFragment.extraction_version == "sent-v1",
                    ReviewFragment.embedding_model_revision
                    == state.get("embedding_model"),
                )
                .order_by(ReviewFragment.review_id, ReviewFragment.start)
                if reviews
                else select(ReviewFragment).where(False)
            )
        ).scalars().all()
        review_by_id = {r.id: r for r in reviews}

        inputs = [
            FragmentInput(
                fragment_id=str(f.id),
                review_id=str(f.review_id),
                text=f.text,
                rating=float(review_by_id[f.review_id].rating)
                if f.review_id in review_by_id and review_by_id[f.review_id].rating is not None
                else None,
                language=review_by_id[f.review_id].language
                if f.review_id in review_by_id
                else None,
                embedding=list(f.embedding),
            )
            for f in fragments
            if f.embedding is not None
        ]
        denominator = len(reviews)
        drafts, other_count, unclassified = cluster_fragments(inputs, denominator)

    cluster_dicts = [
        draft_to_dict(f"cluster_{index}", draft)
        for index, draft in enumerate(drafts)
    ]
    summary = {
        "clustering_version": CLUSTERING_VERSION,
        "clusters": cluster_dicts,
        "other_cluster_review_count": other_count,
        "unclassified_review_count": unclassified,
        "denominator": denominator,
    }
    updates = {
        "clusters": cluster_dicts,
        "other_cluster_review_count": other_count,
        "unclassified_review_count": unclassified,
    }
    return dump_summary(summary), updates

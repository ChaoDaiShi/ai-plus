"""embedding 节点：句子级片段提取 + Provider 向量化，落 review_fragments。

片段保留 (start, end) 码点偏移与 extraction_version 可追溯；同一评论的
同版本片段重复分析时复用已有行，避免跨快照重复。向量维度固定 1024
（pgvector Vector(1024) 列约束）。
"""

import re
import uuid

from sqlalchemy import select

from app.agent.nodes.common import dump_summary
from app.agent.providers.embedding import (
    EMBEDDING_DIM,
    get_embedding_provider,
)
from app.db.models import Review, ReviewFragment, SnapshotReview

EXTRACTION_VERSION = "sent-v1"
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
MIN_FRAGMENT_LEN = 15
MAX_FRAGMENTS_PER_REVIEW = 6


def split_fragments(text: str) -> list[tuple[int, int, str]]:
    """码点偏移句子切分；过短句子并入前段；上限 MAX_FRAGMENTS_PER_REVIEW。"""
    if len(text) < 25:
        return [(0, len(text), text)]
    raw_pieces: list[tuple[int, int, str]] = []
    offset = 0
    for piece in SENTENCE_SPLIT_RE.split(text):
        if not piece:
            continue
        start = text.index(piece, offset)
        raw_pieces.append((start, start + len(piece), piece))
        offset = start + len(piece)
    merged: list[tuple[int, int, str]] = []
    for start, end, piece in raw_pieces:
        if merged and (len(piece) < MIN_FRAGMENT_LEN or len(merged[-1][2]) < MIN_FRAGMENT_LEN):
            prev_start, _, prev_text = merged[-1]
            joined = text[prev_start:end]
            merged[-1] = (prev_start, end, joined)
        else:
            merged.append((start, end, piece))
        if len(merged) >= MAX_FRAGMENTS_PER_REVIEW:
            break
    if len(merged) == MAX_FRAGMENTS_PER_REVIEW:
        last_start = merged[-1][0]
        merged[-1] = (last_start, len(text), text[last_start:])
    return merged


async def run(session_factory, state: dict) -> tuple[dict, dict]:
    tenant_id = uuid.UUID(state["tenant_id"])
    snapshot_id = uuid.UUID(state["snapshot_id"])
    product_id = uuid.UUID(state["product_id"])

    provider = get_embedding_provider()
    if provider.dim != EMBEDDING_DIM:
        raise RuntimeError(
            f"向量维度必须为 {EMBEDDING_DIM}，Provider 返回 {provider.dim}"
        )

    async with session_factory() as session, session.begin():
        negative_reviews = (
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

        existing = (
            await session.execute(
                select(ReviewFragment).where(
                    ReviewFragment.review_id.in_([r.id for r in negative_reviews]),
                    ReviewFragment.extraction_version == EXTRACTION_VERSION,
                    # 换模型不复用旧向量
                    ReviewFragment.embedding_model_revision
                    == provider.model_revision,
                )
                if negative_reviews
                else select(ReviewFragment).where(False)
            )
        ).scalars().all()
        existing_by_key = {
            (f.review_id, f.start, f.end): f for f in existing
        }

        pending: list[tuple[str, ReviewFragment]] = []
        for review in negative_reviews:
            for start, end, piece in split_fragments(review.raw_text):
                key = (review.id, start, end)
                if key in existing_by_key:
                    continue
                fragment = ReviewFragment(
                    tenant_id=tenant_id,
                    review_id=review.id,
                    start=start,
                    end=end,
                    text=piece,
                    extraction_version=EXTRACTION_VERSION,
                    embedding_model_revision=provider.model_revision,
                )
                session.add(fragment)
                pending.append((piece, fragment))
        if pending:
            vectors = await provider.embed([text for text, _ in pending])
            for (text, fragment), vector in zip(pending, vectors, strict=True):
                fragment.embedding = vector
        await session.flush()

    summary = {
        "fragments": len(pending),
        "reused_fragments": len(existing_by_key),
        "embedding_model": provider.model_revision,
        "embedding_mode": "demo" if provider.model_revision.startswith("deterministic") else "bge_m3",
        "dim": EMBEDDING_DIM,
    }
    updates = {
        "embedding_count": len(pending) + len(existing_by_key),
        "embedding_model": provider.model_revision,
    }
    return dump_summary(summary), updates

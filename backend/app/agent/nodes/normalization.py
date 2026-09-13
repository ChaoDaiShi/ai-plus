"""normalization 节点：评论清洗、去重与覆盖统计（任务 §7）。

规则确定性：空文本/过短无缺陷信息/无意义短评/非法星级剔除，同文本重复
只保留最早一条；全部剔除写入 SnapshotReview.exclusion_reason 可核对。
统计口径遵循 api.md §5.1：raw = valid + excluded，negative 为 valid 中
1–3 星。聚类范围为有效 1–3 星评论（技术方案 §5.2）。
"""

import uuid

from sqlalchemy import select, update

from app.agent.nodes.common import content_hash, dump_summary
from app.db.models import DataSnapshot, Review, SnapshotReview

MEANINGLESS_TEXTS = frozenset(
    {"ok", "good", "nice", "great", "fine", "fast", "meh", "bad", "cool", "works"}
)
MIN_TEXT_LEN = 10
# 过短文本若含缺陷信息不能仅按长度删除（技术方案 §5.2）。
DEFECT_HINTS = frozenset(
    """broken broke crack cracked snap snapped leak leaks failed fail broken
    missing smells smell odor damaged damage""".split()
)


def normalize_one(text: str, rating) -> str | None:
    """返回排除原因；None 表示保留。rating 校验 1~5。"""
    stripped = (text or "").strip()
    if not stripped:
        return "empty_text"
    lowered = stripped.lower()
    tokens = set(lowered.split())
    if lowered in MEANINGLESS_TEXTS or tokens <= MEANINGLESS_TEXTS:
        return "meaningless"
    if len(stripped) < MIN_TEXT_LEN and not (tokens & DEFECT_HINTS):
        return "too_short"
    try:
        rating_value = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        return "invalid_rating"
    if rating_value is None or not (1.0 <= rating_value <= 5.0):
        return "invalid_rating"
    return None


def distribution(reviews: list) -> dict:
    """有效评论的星级/语言/月份分布（api.md §5.1 coverage 口径）。"""
    rating_dist: dict[str, int] = {str(star): 0 for star in range(1, 6)}
    language_dist: dict[str, int] = {}
    month_dist: dict[str, int] = {}
    for review in reviews:
        rating_dist[str(int(float(review.rating)))] = (
            rating_dist.get(str(int(float(review.rating))), 0) + 1
        )
        language = review.language or "und"
        language_dist[language] = language_dist.get(language, 0) + 1
        if review.reviewed_at is not None:
            month = review.reviewed_at.strftime("%Y-%m")
            month_dist[month] = month_dist.get(month, 0) + 1
    return rating_dist, language_dist, month_dist


async def run(session_factory, state: dict) -> tuple[dict, dict]:
    snapshot_id = uuid.UUID(state["snapshot_id"])

    async with session_factory() as session, session.begin():
        rows = (
            await session.execute(
                select(SnapshotReview, Review)
                .join(Review, SnapshotReview.review_id == Review.id)
                .where(SnapshotReview.snapshot_id == snapshot_id)
                .order_by(Review.reviewed_at.asc().nulls_last(), Review.id.asc())
            )
        ).all()
        raw_count = len(rows)

        seen_hashes: set[str] = set()
        valid: list[Review] = []
        exclusion_counts: dict[str, int] = {}
        for snapshot_review, review in rows:
            reason: str | None = None
            if review.content_hash in seen_hashes:
                reason = "duplicate_content"
            else:
                reason = normalize_one(review.raw_text, review.rating)
            if reason is None:
                seen_hashes.add(review.content_hash)
                valid.append(review)
            else:
                exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
                await session.execute(
                    update(SnapshotReview)
                    .where(SnapshotReview.id == snapshot_review.id)
                    .values(included=False, exclusion_reason=reason)
                )

        negative = [r for r in valid if float(r.rating) <= 3.0]
        rating_dist, language_dist, month_dist = distribution(valid)
        coverage = {
            "raw_count": raw_count,
            "valid_count": len(valid),
            "excluded_count": raw_count - len(valid),
            "negative_count": len(negative),
            "rating_distribution": rating_dist,
            "language_distribution": language_dist,
            "month_distribution": month_dist,
            "missing_reasons": exclusion_counts,
            "sampling_mode": "full_window",
        }
        await session.execute(
            update(DataSnapshot)
            .where(DataSnapshot.id == snapshot_id)
            .values(coverage=coverage)
        )
        await session.flush()

    summary = {
        "raw_count": raw_count,
        "valid_count": len(valid),
        "filtered_count": raw_count - len(valid),
        "negative_count": len(negative),
        "exclusion_reasons": exclusion_counts,
    }
    updates = {
        "raw_count": raw_count,
        "valid_count": len(valid),
        "filtered_count": raw_count - len(valid),
        "negative_count": len(negative),
    }
    return dump_summary(summary), updates

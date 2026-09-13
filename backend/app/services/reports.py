"""报告组装服务（api.md §5）：从持久化行构建响应，不动态拼假数据。

所有字段来源于 reports / issue_clusters / cluster_members /
reform_proposals / proposal_issues / data_snapshots / reviews；
metrics 按有效评论实时计算并标注样本口径；reform_potential_index 与
fba_savings_per_unit 在 P0 明确返回 NOT_EVALUATED。
"""

import base64
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ClusterMember,
    DataSnapshot,
    IssueCluster,
    Product,
    ProductSnapshot,
    ProposalIssue,
    ReformProposal,
    Report,
    Review,
    ReviewFragment,
    SnapshotReview,
    Task,
    TaskItem,
)
from app.services.tasks import TERMINAL_STATUSES


class ReportNotReady(Exception):
    """任务尚未终结且无报告。"""


class ReportNotAvailable(Exception):
    """任务已终结但没有可用报告。"""


class NotFound(Exception):
    """任务/分项/报告/目标不存在或不属于当前租户。"""


def source_mode_of(snapshot: DataSnapshot) -> str:
    return "DEMO_DATASET" if snapshot.source == "demo_dataset" else "LIVE_API"


def embedding_mode_of(model_version: str) -> str:
    return "demo" if model_version.startswith("deterministic") else "bge_m3"


def encode_cursor(review_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(str(review_id).encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> uuid.UUID:
    try:
        return uuid.UUID(
            base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("非法分页游标") from exc


def _metric(value, reason: str, sample_count: int | None, denominator: int | None) -> dict:
    return {
        "value": value,
        "reason": reason,
        "basis": (
            None
            if sample_count is None and denominator is None
            else {"sample_count": sample_count, "denominator": denominator}
        ),
    }


async def load_report(
    session: AsyncSession, tenant_id: uuid.UUID, task_id: uuid.UUID, item_id: uuid.UUID
) -> tuple[Report, Task, TaskItem]:
    """定位报告：校验租户与 task↔item 归属；无报告按任务状态抛对应异常。"""
    task = (
        await session.execute(
            select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if task is None:
        raise NotFound("任务不存在或不属于当前企业")
    item = (
        await session.execute(
            select(TaskItem).where(
                TaskItem.id == item_id,
                TaskItem.task_id == task_id,
                TaskItem.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFound("分项不存在或不属于该任务")
    report = (
        await session.execute(
            select(Report)
            .where(Report.item_id == item_id)
            .order_by(Report.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if report is None:
        if task.status in TERMINAL_STATUSES:
            raise ReportNotAvailable()
        raise ReportNotReady()
    return report, task, item


async def build_report_payload(
    session: AsyncSession, report: Report, task: Task, item: TaskItem
) -> dict:
    snapshot = (
        await session.execute(
            select(DataSnapshot).where(DataSnapshot.id == report.snapshot_id)
        )
    ).scalar_one()
    product = (
        await session.execute(select(Product).where(Product.id == item.product_id))
    ).scalar_one()
    product_snapshot = (
        await session.execute(
            select(ProductSnapshot).where(
                ProductSnapshot.id == snapshot.product_snapshot_id
            )
        )
    ).scalar_one_or_none()

    # 有效评论集合与 metrics 口径（coverage 统计于 normalization 节点）。
    valid_reviews = (
        await session.execute(
            select(Review)
            .join(SnapshotReview, SnapshotReview.review_id == Review.id)
            .where(
                SnapshotReview.snapshot_id == snapshot.id,
                SnapshotReview.included.is_(True),
            )
            .order_by(Review.id)
        )
    ).scalars().all()
    valid_count = len(valid_reviews)
    ratings = [float(r.rating) for r in valid_reviews if r.rating is not None]
    negative_count = sum(1 for r in ratings if r <= 3.0)
    average_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
    negative_rate = round(negative_count / len(ratings), 4) if ratings else None

    cluster_rows = (
        await session.execute(
            select(IssueCluster)
            .where(IssueCluster.report_id == report.id)
            .order_by(IssueCluster.frequency.desc(), IssueCluster.severity.desc())
        )
    ).scalars().all()

    cluster_ids = [c.id for c in cluster_rows]
    member_counts = await _evidence_counts_by_cluster(session, cluster_ids)
    sample_quotes = await _sample_quotes_by_cluster(session, cluster_ids)

    clusters_payload = []
    for cluster in cluster_rows:
        clusters_payload.append(
            {
                "id": str(cluster.id),
                "name_zh": cluster.name_zh,
                "name_en": cluster.name_en,
                "category": cluster.category,
                "frequency": cluster.frequency,
                "denominator": cluster.denominator,
                "share_ratio": (
                    round(cluster.frequency / cluster.denominator, 4)
                    if cluster.denominator
                    else None
                ),
                "severity": cluster.severity,
                "severity_reason": cluster.severity_reason,
                "sample_quote": sample_quotes.get(cluster.id),
                "evidence_count": member_counts.get(cluster.id, 0),
                "photo_count": 0,
            }
        )

    proposal_rows = (
        await session.execute(
            select(ReformProposal)
            .where(ReformProposal.report_id == report.id)
            .order_by(ReformProposal.column, ReformProposal.id)
        )
    ).scalars().all()
    proposal_cluster_ids = await _proposal_cluster_map(
        session, [p.id for p in proposal_rows]
    )
    proposals_payload: dict[str, list] = {"product": [], "packaging": []}
    for proposal in proposal_rows:
        cluster_id_list = proposal_cluster_ids.get(proposal.id, [])
        evidence_count = await _proposal_evidence_count(session, cluster_id_list)
        key = "product" if proposal.column == "PRODUCT" else "packaging"
        proposals_payload[key].append(
            {
                "id": str(proposal.id),
                "column": proposal.column,
                "title": proposal.title,
                "action": proposal.action,
                "target_cluster_ids": [str(cid) for cid in cluster_id_list],
                "expected_effect": proposal.expected_effect,
                "assumptions": proposal.assumptions,
                "verification_required": proposal.verification_required,
                "evidence_count": evidence_count,
                "photo_count": 0,
            }
        )

    coverage = dict(snapshot.coverage or {})
    if not coverage:
        coverage = {
            "raw_count": 0,
            "valid_count": 0,
            "excluded_count": 0,
            "negative_count": 0,
            "rating_distribution": {},
            "language_distribution": {},
            "month_distribution": {},
            "missing_reasons": {},
            "sampling_mode": "full_window",
        }

    return {
        "report_id": str(report.id),
        "report_version": report.version,
        "item_id": str(item.id),
        "task_id": str(task.id),
        "asin": product.asin,
        "published_at": report.published_at,
        "source_mode": source_mode_of(snapshot),
        "snapshot": {
            "id": str(snapshot.id),
            "source": snapshot.source,
            "observed_at": snapshot.observed_at,
            "window": {
                "start_date": snapshot.window_start,
                "end_date": snapshot.window_end,
            },
            "content_hash": snapshot.content_hash,
        },
        "product": {
            "asin": product.asin,
            "marketplace": product.marketplace,
            "title": product_snapshot.title if product_snapshot else None,
            "price": (
                float(product_snapshot.price)
                if product_snapshot and product_snapshot.price is not None
                else None
            ),
            "currency": product_snapshot.currency if product_snapshot else None,
            "bsr": product_snapshot.bsr if product_snapshot else None,
            "observed_at": product_snapshot.observed_at if product_snapshot else None,
        },
        "availability": report.availability,
        "limitations": report.limitations,
        "coverage": coverage,
        "metrics": {
            "sample_average_rating": _metric(
                average_rating, "样本平均星级（1–5）", valid_count, valid_count
            ),
            "sample_negative_rate": _metric(
                negative_rate, "有效评论中 1–3 星占比", negative_count, len(ratings)
            ),
            "issue_count": _metric(
                len(cluster_rows), "聚类得到的痛点簇数量", negative_count, valid_count
            ),
            "reform_potential_index": {
                "value": None,
                "reason": "NOT_EVALUATED",
                "basis": None,
            },
            "fba_savings_per_unit": {
                "value": None,
                "reason": "NOT_EVALUATED",
                "basis": None,
            },
        },
        "clusters": clusters_payload,
        "proposals": proposals_payload,
        "veto_status": "NOT_EVALUATED",
        "provenance": {
            "embedding_model_revision": report.model_version,
            "embedding_mode": embedding_mode_of(report.model_version),
            "llm_model_id": report.llm_model_id,
            "prompt_version": report.prompt_version,
            "pipeline_version": report.pipeline_version,
            "clustering_version": report.clustering_version,
            "cleaning_version": snapshot.cleaning_version,
        },
    }


async def _evidence_counts_by_cluster(
    session: AsyncSession, cluster_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not cluster_ids:
        return {}
    rows = await session.execute(
        select(
            ClusterMember.cluster_id,
            func.count(func.distinct(ReviewFragment.review_id)),
        )
        .join(ReviewFragment, ClusterMember.fragment_id == ReviewFragment.id)
        .where(ClusterMember.cluster_id.in_(cluster_ids))
        .group_by(ClusterMember.cluster_id)
    )
    return {cluster_id: count for cluster_id, count in rows.all()}


async def _sample_quotes_by_cluster(
    session: AsyncSession, cluster_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict]:
    if not cluster_ids:
        return {}
    rows = await session.execute(
        select(ClusterMember.cluster_id, ReviewFragment, Review)
        .join(ReviewFragment, ClusterMember.fragment_id == ReviewFragment.id)
        .join(Review, ReviewFragment.review_id == Review.id)
        .where(ClusterMember.cluster_id.in_(cluster_ids))
        .order_by(ClusterMember.cluster_id, ReviewFragment.id)
    )
    quotes: dict[uuid.UUID, dict] = {}
    for cluster_id, fragment, review in rows.all():
        if cluster_id in quotes:
            continue
        quotes[cluster_id] = {
            "review_id": str(review.id),
            "text": fragment.text,
            "translation": None,
        }
    return quotes


async def _proposal_cluster_map(
    session: AsyncSession, proposal_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    if not proposal_ids:
        return {}
    rows = await session.execute(
        select(ProposalIssue).where(ProposalIssue.proposal_id.in_(proposal_ids))
    )
    mapping: dict[uuid.UUID, list[uuid.UUID]] = {}
    for issue in rows.scalars().all():
        mapping.setdefault(issue.proposal_id, []).append(issue.cluster_id)
    return mapping


async def _proposal_evidence_count(
    session: AsyncSession, cluster_ids: list[uuid.UUID]
) -> int:
    if not cluster_ids:
        return 0
    result = await session.execute(
        select(func.count(func.distinct(ReviewFragment.review_id)))
        .select_from(ClusterMember)
        .join(ReviewFragment, ClusterMember.fragment_id == ReviewFragment.id)
        .where(ClusterMember.cluster_id.in_(cluster_ids))
    )
    return result.scalar() or 0


async def build_evidence_page(
    session: AsyncSession,
    report: Report,
    *,
    cluster_id: uuid.UUID | None,
    proposal_id: uuid.UUID | None,
    cursor: uuid.UUID | None,
    limit: int,
) -> dict:
    """证据反查（api.md §5.2）：cluster/proposal 二选一，按评论去重分页。"""
    if cluster_id is not None:
        target_cluster = (
            await session.execute(
                select(IssueCluster).where(
                    IssueCluster.id == cluster_id,
                    IssueCluster.report_id == report.id,
                )
            )
        ).scalar_one_or_none()
        if target_cluster is None:
            raise NotFound("痛点簇不属于该报告")
        member_stmt = (
            select(ReviewFragment, Review)
            .join(ClusterMember, ClusterMember.fragment_id == ReviewFragment.id)
            .join(Review, ReviewFragment.review_id == Review.id)
            .where(ClusterMember.cluster_id == cluster_id)
        )
        target = {"type": "cluster", "id": str(cluster_id)}
    else:
        proposal = (
            await session.execute(
                select(ReformProposal).where(
                    ReformProposal.id == proposal_id,
                    ReformProposal.report_id == report.id,
                )
            )
        ).scalar_one_or_none()
        if proposal is None:
            raise NotFound("建议不属于该报告")
        linked_cluster_ids = (
            await session.execute(
                select(ProposalIssue.cluster_id).where(
                    ProposalIssue.proposal_id == proposal_id
                )
            )
        ).scalars().all()
        member_stmt = (
            select(ReviewFragment, Review)
            .join(ClusterMember, ClusterMember.fragment_id == ReviewFragment.id)
            .join(Review, ReviewFragment.review_id == Review.id)
            .where(ClusterMember.cluster_id.in_(linked_cluster_ids))
            if linked_cluster_ids
            else None
        )
        target = {"type": "proposal", "id": str(proposal_id)}

    asin_row = await session.execute(
        select(Product.asin)
        .join(TaskItem, TaskItem.product_id == Product.id)
        .where(TaskItem.id == report.item_id)
    )
    asin = asin_row.scalar_one_or_none()

    # 去重按评论（一条评论可能贡献多个片段）；页内取首片段作为引用文本。
    by_review: dict[uuid.UUID, dict] = {}
    if member_stmt is not None:
        rows = (
            await session.execute(member_stmt.order_by(Review.id, ReviewFragment.id))
        ).all()
        for fragment, review in rows:
            if review.id in by_review:
                continue
            by_review[review.id] = {
                "review_id": str(review.id),
                "source_review_id": review.source_review_id,
                "asin": asin,
                "source_url": review.source_url,
                "rating": float(review.rating) if review.rating is not None else None,
                "language": review.language,
                "reviewed_at": review.reviewed_at,
                "observed_at": review.observed_at,
                "text": fragment.text,
                "translation": None,
                "images": [],
            }
    ordered = sorted(by_review.items(), key=lambda kv: kv[0])
    total = len(ordered)
    after = ordered if cursor is None else [kv for kv in ordered if kv[0] > cursor]
    page = after[:limit]
    next_cursor = encode_cursor(page[-1][0]) if len(after) > limit and page else None

    return {
        "report_id": str(report.id),
        "target": target,
        "total": total,
        "items": [entry for _, entry in page],
        "next_cursor": next_cursor,
    }

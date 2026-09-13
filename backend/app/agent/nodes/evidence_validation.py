"""evidence_validation 节点：MVP 防幻觉门（任务 §13）。

逐条 Proposal 验证 proposal → cluster → review_id → Review 行：
1. target_cluster_keys 必须指向本报告聚类草稿；
2. evidence_review_ids 必须是所引用簇评论的子集；
3. 全部 review_id 必须真实存在于数据库。
任一失败抛 EvidenceValidationError（永久错误），本 attempt 不得 publish。
"""

import uuid

from sqlalchemy import select

from app.agent.nodes.common import dump_summary
from app.db.models import Review


class EvidenceValidationError(Exception):
    """证据校验失败：阻止报告发布。"""


async def run(session_factory, state: dict) -> tuple[dict, dict]:
    clusters = {c["key"]: c for c in state.get("clusters", [])}
    proposals = state.get("proposals", [])
    errors: list[str] = []

    for proposal in proposals:
        pid = proposal["key"]
        targets = proposal.get("target_cluster_keys", [])
        if not targets:
            errors.append(f"{pid}: 未引用任何痛点簇")
            continue
        missing_clusters = [key for key in targets if key not in clusters]
        if missing_clusters:
            errors.append(f"{pid}: 引用了不存在的簇 {missing_clusters}")
            continue
        cluster_reviews: set[str] = set()
        for key in targets:
            cluster_reviews.update(clusters[key]["review_ids"])
        evidence = proposal.get("evidence_review_ids", [])
        outside = [rid for rid in evidence if rid not in cluster_reviews]
        if outside:
            errors.append(f"{pid}: 证据引用超出所属簇范围 {outside[:5]}")

    referenced = sorted(
        {rid for p in proposals for rid in p.get("evidence_review_ids", [])}
        | {rid for c in clusters.values() for rid in c["review_ids"]}
    )
    existing: set[str] = set()
    if referenced:
        async with session_factory() as session:
            rows = await session.execute(
                select(Review.id).where(
                    Review.id.in_([uuid.UUID(rid) for rid in referenced])
                )
            )
            existing = {str(row[0]) for row in rows.all()}
    not_found = [rid for rid in referenced if rid not in existing]
    if not_found:
        errors.append(f"评论引用在数据库中不存在：{not_found[:5]}")

    if errors:
        raise EvidenceValidationError("；".join(errors))

    summary = {
        "proposals_checked": len(proposals),
        "cluster_refs_checked": sum(len(p.get("target_cluster_keys", [])) for p in proposals),
        "review_refs_checked": len(referenced),
        "result": "passed",
    }
    updates = {"evidence_report": {"result": "passed", "checked": len(referenced)}}
    return dump_summary(summary), updates

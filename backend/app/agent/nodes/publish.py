"""publish 节点：单事务发布不可变报告（任务 §14）。

与取消串行（api.md §7.1）：发布事务内复查 cancel_requested_at，
先提交取消则不再发布新报告。零样本/无簇时发布 INSUFFICIENT 报告，
limitations 如实声明数据来源与 P0 未评估项，禁止假数字。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ClusterMember,
    DataSnapshot,
    IssueCluster,
    ProposalIssue,
    ReformProposal,
    Report,
    Task,
)

PIPELINE_VERSION = "p0-mvp-1"
SUFFICIENT_MIN_VALID = 20
TRACK_TO_COLUMN = {
    "BODY_OPTIMIZATION": "PRODUCT",
    "PACKAGING_FULFILLMENT": "PACKAGING",
}

VERIFICATION_BY_TRACK = {
    "BODY_OPTIMIZATION": ["样件载荷与疲劳测试", "开模前工程评审"],
    "PACKAGING_FULFILLMENT": ["ISTA 系列运输跌落测试", "首件装配与履约试单"],
}


class CancelRequestedError(Exception):
    """发布前发现取消请求：放弃发布，分项按 CANCELED 终结。"""


def decide_availability(valid_count: int, cluster_count: int) -> str:
    if valid_count == 0 or cluster_count == 0:
        return "INSUFFICIENT"
    if valid_count < SUFFICIENT_MIN_VALID:
        return "LIMITED"
    return "SUFFICIENT"


def build_limitations(
    source: str | None, proposal_provider: str | None, valid_count: int
) -> list[str]:
    limitations: list[str] = []
    if source == "demo_dataset":
        limitations.append("当前使用固定演示数据集，不代表实时 Amazon 数据")
    else:
        limitations.append("结论仅基于单次采集快照，不代表长期口碑分布")
    limitations.append(
        f"样本量为 {valid_count} 条有效评论，属抽样证据，不能推断总体质量"
    )
    limitations.append("建议由规则引擎基于痛点聚类生成，需工厂打样验证后采用")
    limitations.append("改款潜力指数与 FBA 节约额为 P1 财务能力，本次未评估")
    limitations.append("P0 未纳入图片取证，photo_count=0 不代表来源页面没有图片")
    if proposal_provider == "rule_based":
        limitations.append("未配置 LLM，建议文案由确定性规则生成")
    return limitations


async def _insert_report(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    state: dict,
) -> Report:
    clusters = state.get("clusters", [])
    proposals = state.get("proposals", [])
    valid_count = int(state.get("valid_count") or 0)
    availability = decide_availability(valid_count, len(clusters))
    embedding_model = state.get("embedding_model") or "unknown"

    report = Report(
        tenant_id=tenant_id,
        item_id=item_id,
        version=1,
        snapshot_id=uuid.UUID(state["snapshot_id"]),
        pipeline_version=PIPELINE_VERSION,
        model_version=embedding_model,
        llm_model_id=state.get("proposal_provider") or None,
        prompt_version=state.get("proposal_version") or "rule-proposal-v1",
        clustering_version=state.get("clustering_version") or None,
        availability=availability,
        limitations=build_limitations(
            state.get("source"), state.get("proposal_provider"), valid_count
        ),
        published_at=datetime.now(timezone.utc),
    )
    session.add(report)
    await session.flush()

    cluster_id_by_key: dict[str, uuid.UUID] = {}
    for draft in clusters:
        row = IssueCluster(
            tenant_id=tenant_id,
            report_id=report.id,
            name_zh=draft["name_zh"],
            name_en=draft["name_en"],
            category=draft["category"],
            frequency=draft["frequency"],
            denominator=draft["denominator"],
            severity=draft["severity"],
            severity_reason=draft["severity_reason"],
        )
        session.add(row)
        await session.flush()
        cluster_id_by_key[draft["key"]] = row.id
        for fragment_id in draft["fragment_ids"]:
            session.add(
                ClusterMember(cluster_id=row.id, fragment_id=uuid.UUID(fragment_id))
            )

    for draft in proposals:
        proposal = ReformProposal(
            tenant_id=tenant_id,
            report_id=report.id,
            column=TRACK_TO_COLUMN[draft["track_type"]],
            title=draft["title_zh"],
            action=draft["recommendation"],
            expected_effect=draft["expected_effect"],
            verification_required=VERIFICATION_BY_TRACK[draft["track_type"]],
            assumptions=[
                f"问题定性：{draft['problem']}",
                f"成本量级：{draft['cost_level']}（未核算，需工程确认）",
            ],
        )
        session.add(proposal)
        await session.flush()
        for key in draft["target_cluster_keys"]:
            cluster_id = cluster_id_by_key.get(key)
            if cluster_id is None:
                raise RuntimeError(f"建议 {draft['key']} 引用了不存在的簇 {key}")
            session.add(ProposalIssue(proposal_id=proposal.id, cluster_id=cluster_id))
    await session.flush()
    return report


async def run(session_factory, state: dict) -> tuple[dict, dict]:
    tenant_id = uuid.UUID(state["tenant_id"])
    task_id = uuid.UUID(state["task_id"])
    item_id = uuid.UUID(state["item_id"])

    async with session_factory() as session, session.begin():
        # 发布与取消串行检查：取消标记先提交则不再发布（api.md §7.1）。
        task = (
            await session.execute(
                select(Task).where(Task.id == task_id).with_for_update()
            )
        ).scalar_one()
        if task.cancel_requested_at is not None:
            raise CancelRequestedError("取消请求已提交，放弃发布")

        report = await _insert_report(session, tenant_id=tenant_id, item_id=item_id, state=state)

    summary = {
        "report_id": str(report.id),
        "availability": report.availability,
        "clusters": len(state.get("clusters", [])),
        "proposals": len(state.get("proposals", [])),
    }
    updates = {"report_id": str(report.id)}
    return summary, updates

"""节点执行上下文：LangGraph 节点包装层，承载既有 Worker 执行语义。

职责划分（任务 §5）：Worker/本上下文负责任务领取后的租约校验、取消协作、
恢复复用、重试分类与节点行/事件持久化；LangGraph 只负责业务节点编排；
Service/Provider 负责节点业务逻辑。本文件不改写 app.worker.graph 既有
语义，只是把逐节点执行体挂到 StateGraph 上。
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.nodes import NODE_ORDER, NODE_PROGRESS
from app.agent.nodes import (
    clustering as clustering_node,
)
from app.agent.nodes import (
    embedding as embedding_node,
)
from app.agent.nodes import (
    evidence_validation as evidence_node,
)
from app.agent.nodes import (
    ingestion as ingestion_node,
)
from app.agent.nodes import (
    normalization as normalization_node,
)
from app.agent.nodes import (
    proposal as proposal_node,
)
from app.agent.nodes import (
    publish as publish_node,
)
from app.agent.nodes.common import NodeDataError, load_node_summary
from app.api.schemas import NodeStatus
from app.services import events as event_svc
from app.services.tasks import TaskStatus, utcnow
from app.worker import graph as worker_graph

BUSINESS_NODES = {
    "ingestion": ingestion_node.run,
    "normalization": normalization_node.run,
    "embedding": embedding_node.run,
    "clustering": clustering_node.run,
    "proposal": proposal_node.run,
    "evidence_validation": evidence_node.run,
    "publish": publish_node.run,
}

# 恢复水合：state 缺失时从上游节点 output_summary 重建衔接数据。
HYDRATION: dict[str, list[tuple[str, str, str]]] = {
    "normalization": [("snapshot_id", "ingestion", "snapshot_id")],
    "embedding": [("snapshot_id", "ingestion", "snapshot_id")],
    "clustering": [
        ("snapshot_id", "ingestion", "snapshot_id"),
        ("embedding_model", "embedding", "embedding_model"),
    ],
    "proposal": [("clusters", "clustering", "clusters")],
    "evidence_validation": [
        ("clusters", "clustering", "clusters"),
        ("proposals", "proposal", "drafts"),
    ],
    "publish": [
        ("snapshot_id", "ingestion", "snapshot_id"),
        ("clusters", "clustering", "clusters"),
        ("proposals", "proposal", "drafts"),
        ("valid_count", "normalization", "valid_count"),
        ("raw_count", "ingestion", "raw_count"),
        ("source", "ingestion", "source"),
        ("embedding_model", "embedding", "embedding_model"),
        ("clustering_version", "clustering", "clustering_version"),
        ("proposal_provider", "proposal", "provider"),
        ("proposal_version", "proposal", "proposal_version"),
    ],
}


class NodeRunContext:
    """单分项执行上下文：LangGraph 每个节点的持久化与守卫包装。"""

    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory,
        tenant_id: uuid.UUID,
        task_id: uuid.UUID,
        item_id: uuid.UUID,
        product_id: uuid.UUID,
        attempt: int,
        worker_id: str,
        lease_version: int,
        node_outcomes: dict[str, dict] | None,
        sleep,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.tenant_id = tenant_id
        self.task_id = task_id
        self.item_id = item_id
        self.product_id = product_id
        self.attempt = attempt
        self.worker_id = worker_id
        self.lease_version = lease_version
        self.node_outcomes = node_outcomes
        self.sleep = sleep

    async def _cancel_requested(self) -> bool:
        return (
            await worker_graph._cancel_requested(self.session, self.tenant_id, self.task_id)
        ) is not None

    async def _lease_ok(self) -> bool:
        return await worker_graph._lease_ok(
            self.session, self.item_id, self.worker_id, self.lease_version
        )

    async def _hydrate(self, node: str, state: dict) -> dict:
        """恢复路径：从上游节点 output_summary 重建缺失的衔接数据。"""
        updates: dict[str, Any] = {}
        for state_key, source_node, summary_key in HYDRATION.get(node, []):
            if state.get(state_key) not in (None, [], ""):
                continue
            async with self.session.begin():
                summary = await load_node_summary(
                    self.session, self.item_id, self.attempt, source_node
                )
            if summary is None or summary.get(summary_key) in (None, [], ""):
                raise NodeDataError(
                    f"节点 {node} 缺少上游 {source_node} 的 {summary_key}，无法继续"
                )
            updates[state_key] = summary[summary_key]
        return updates

    async def _emit(self, *, node: str, status: str, extra: dict | None = None) -> None:
        payload = {"node": node, "status": status}
        if extra:
            payload.update(extra)
        await event_svc.append_event(
            self.session,
            tenant_id=self.tenant_id,
            task_id=self.task_id,
            event_type="node.updated",
            payload=payload,
            item_id=self.item_id,
            attempt=self.attempt,
        )

    async def _existing_rows(self, node: str) -> list:
        return await worker_graph._existing_versions(
            self.session, self.item_id, self.attempt, node
        )

    async def run_node(self, node: str, index: int, state: dict) -> dict:
        """LangGraph 节点包装：守卫 → 恢复 → 业务执行 → 行与事件持久化。

        返回状态增量；需要中止图时设置 stop_reason（条件边路由到 END）。
        """
        base = {"current_node": node, "node_index": index, "progress": NODE_PROGRESS[node]}
        if await self._cancel_requested():
            return {**base, "stop_reason": "canceled"}
        if not await self._lease_ok():
            return {**base, "stop_reason": "stolen"}
        existing = await self._existing_rows(node)
        if any(r.status == TaskStatus.COMPLETED.value for r in existing):
            # 恢复：复用已提交产物，不重新执行、不补发事件。
            return {**base, "current_node": None}
        version = f"v{len(existing) + 1}"

        fixture_outcome = (
            self.node_outcomes.get(node) if self.node_outcomes is not None else None
        )

        if fixture_outcome is not None and fixture_outcome["status"] == "skipped":
            row, inserted = await worker_graph._write_node_row(
                self.session,
                tenant_id=self.tenant_id,
                item_id=self.item_id,
                attempt=self.attempt,
                node=node,
                status=NodeStatus.SKIPPED.value,
                started_at=None,
                completed_at=utcnow(),
                duration_ms=fixture_outcome.get("duration_ms"),
                output_version=version,
                output_summary=None,
                skip_reason=fixture_outcome.get("skip_reason"),
            )
            if inserted:
                await self._emit(
                    node=node,
                    status=row.status,
                    extra={
                        "duration_ms": row.duration_ms,
                        "skip_reason": row.skip_reason,
                    },
                )
            return {**base, "current_node": None}

        # 真实执行（或夹具 completed/failed）：开始事件 + 重试循环 + 终版行。
        is_real = fixture_outcome is None
        if is_real:
            await self._emit(node=node, status="RUNNING", extra={"progress": NODE_PROGRESS[node]})
            try:
                state = {**state, **(await self._hydrate(node, state))}
            except NodeDataError as exc:
                return {**base, "stop_reason": "failed", "error": str(exc)}

        outcome_status = TaskStatus.FAILED.value
        summary: dict | None = None
        started = utcnow()
        duration_ms: int | None = None
        error_text: str | None = None
        for try_index in range(1, worker_graph.MAX_NODE_RETRIES + 2):
            started = utcnow()
            kind = "permanent"
            error_text = None
            try:
                if fixture_outcome is not None:
                    if fixture_outcome["status"] == "completed":
                        summary = fixture_outcome.get("output_summary")
                        outcome_status = TaskStatus.COMPLETED.value
                    else:
                        kind = fixture_outcome.get("error_kind", "permanent")
                        error_text = fixture_outcome.get("error", "fixture failure")
                        raise RuntimeError(error_text)
                else:
                    run_business = BUSINESS_NODES[node]
                    summary, updates = await run_business(self.session_factory, {
                        **state,
                        "tenant_id": str(self.tenant_id),
                        "task_id": str(self.task_id),
                        "item_id": str(self.item_id),
                    })
                    state = {**state, **updates}
                    outcome_status = TaskStatus.COMPLETED.value
            except Exception as exc:  # noqa: BLE001 — 统一分类后记录
                if is_real:
                    kind = worker_graph.classify_error(exc)
                if isinstance(exc, publish_node.CancelRequestedError):
                    return {**base, "stop_reason": "canceled"}
                error_text = error_text or str(exc)
                summary = None
                outcome_status = TaskStatus.FAILED.value
            ended = utcnow()
            duration_ms = int((ended - started).total_seconds() * 1000)
            if outcome_status == TaskStatus.COMPLETED.value or kind != "transient":
                break
            if try_index <= worker_graph.MAX_NODE_RETRIES:
                await self.sleep(worker_graph.backoff_delays()[try_index - 1])

        row, inserted = await worker_graph._write_node_row(
            self.session,
            tenant_id=self.tenant_id,
            item_id=self.item_id,
            attempt=self.attempt,
            node=node,
            status=outcome_status,
            started_at=started,
            completed_at=ended,
            duration_ms=duration_ms,
            output_version=version,
            output_summary=summary,
            skip_reason=None,
        )
        if inserted:
            extra = {
                "duration_ms": row.duration_ms,
                "output_summary": summary,
                "progress": NODE_PROGRESS[node],
            }
            if summary and isinstance(summary, dict):
                extra["message"] = _node_message(node, summary)
            await self._emit(node=node, status=row.status, extra=extra)
        if row.status != TaskStatus.COMPLETED.value:
            return {**base, "stop_reason": "failed", "error": error_text or "节点执行失败"}
        return {**base, "current_node": None}


def _node_message(node: str, summary: dict) -> str:
    """节点完成事件的人类可读摘要（SSE payload.message）。"""
    if node == "ingestion":
        return f"Collected {summary.get('raw_count', 0)} raw reviews ({summary.get('source')})"
    if node == "normalization":
        return (
            f"Validated {summary.get('valid_count', 0)}/{summary.get('raw_count', 0)} reviews, "
            f"filtered {summary.get('filtered_count', 0)}"
        )
    if node == "embedding":
        return f"Embedded {summary.get('fragments', 0)} fragments ({summary.get('embedding_model')})"
    if node == "clustering":
        return f"Formed {summary.get('clusters', 0)} pain-point clusters"
    if node == "proposal":
        return (
            f"Generated {summary.get('body', 0)} body + {summary.get('packaging', 0)} "
            f"packaging proposals"
        )
    if node == "evidence_validation":
        return f"Validated {summary.get('review_refs_checked', 0)} evidence references"
    if node == "publish":
        return f"Report published ({summary.get('availability')})"
    return ""

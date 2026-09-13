"""P0 Minimal MVP 端到端验收门（任务 §27）。

全程不访问互联网：Demo Provider + 确定性 1024 维向量 + 规则建议。
流程：POST task → worker poll_once → LangGraph 七节点 → 报告持久化 →
SSE 终态事件 → GET report / evidence 全链路断言。
需隔离 PostgreSQL（TEST_DATABASE_URL / 本地默认库）。
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import (
    ItemNode,
    Report,
    Review,
    Task,
    TaskEvent,
    TaskItem,
)
from app.api.deps import get_current_tenant_id
from app.main import create_app
from app.worker import runner as worker_runner
from tests.support import pg_url, requires_pg, reset_pg, run
from tests.test_tasks import PROJECT_A, TENANT_A, seed_tenant_project

NODES = [
    "ingestion",
    "normalization",
    "embedding",
    "clustering",
    "proposal",
    "evidence_validation",
    "publish",
]


@pytest.fixture()
def e2e(pg_schema):
    from app.db.session import get_session

    app = create_app()
    engine = create_async_engine(pg_url(), poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    async def override_tenant():
        return TENANT_A

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_tenant_id] = override_tenant
    client = TestClient(app)

    async def reset_and_seed():
        session = factory()
        try:
            await reset_pg(session)
            await seed_tenant_project_async(session)
            await session.commit()
        finally:
            await session.close()

    run(reset_and_seed())
    yield client, factory, engine
    app.dependency_overrides.clear()
    run(engine.dispose())


async def seed_tenant_project_async(session):
    from app.db.models import Project, Tenant

    session.add(Tenant(id=TENANT_A, name="t"))
    await session.flush()
    session.add(
        Project(id=PROJECT_A, tenant_id=TENANT_A, name="p", marketplace="US")
    )


def _sse_events(client, task_id, after=0):
    """读取 SSE 流直到 stream.end，返回 (event, data) 列表。"""
    events = []
    with client.stream(
        "GET", f"/api/v1/insight/task/{task_id}/events?after={after}"
    ) as response:
        assert response.status_code == 200
        current = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                current = line[len("event: "):]
            elif line.startswith("data: ") and current is not None:
                events.append((current, line[len("data: "):]))
                current = None
    return events


@requires_pg
def test_p0_mvp_end_to_end(e2e):
    """任务 §27 断言全集：POST → Worker → LangGraph → Report → SSE → UI 数据。"""
    client, factory, engine = e2e

    # 1. 创建任务（§27：POST task）
    created = client.post(
        "/api/v1/insight/task",
        headers={"Idempotency-Key": "e2e-mvp-1"},
        json={"project_id": str(PROJECT_A), "asins": ["B08N5WRWNW"]},
    )
    assert created.status_code == 202, created.text
    body = created.json()
    task_id, item_id = body["task_id"], body["items"][0]["item_id"]

    # 2. Worker 领取并执行 LangGraph（真实节点，非 fixture）
    async def poll():
        session = factory()
        try:
            return await worker_runner.poll_once(session, "e2e-worker")
        finally:
            await session.close()

    assert run(poll()) is True
    assert run(poll()) is False  # 队列清空

    # 3. 任务终态
    snapshot = client.get(f"/api/v1/insight/task/{task_id}")
    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "COMPLETED"

    # 4. 节点行：7 节点全部 COMPLETED，publish 完成（§27：publish node COMPLETED）
    async def check_nodes():
        session = factory()
        try:
            rows = (
                await session.execute(
                    select(ItemNode).where(ItemNode.item_id == uuid.UUID(item_id))
                )
            ).scalars().all()
            return rows
        finally:
            await session.close()

    rows = run(check_nodes())
    by_node = {r.node: r.status for r in rows}
    assert set(by_node) == set(NODES)
    assert all(status == "COMPLETED" for status in by_node.values())

    # 5. SSE 全部节点事件 + 终态（§26-G）
    events = _sse_events(client, task_id)
    event_names = [name for name, _ in events]
    for node in NODES:
        node_events = [
            json.loads(data)
            for name, data in events
            if name == "node.updated"
            and json.loads(data)["payload"]["node"] == node
        ]
        statuses = {e["payload"]["status"] for e in node_events}
        assert node_events, f"缺少节点事件：{node}"
        assert "COMPLETED" in statuses
        if node != "publish":
            assert any(
                e["payload"].get("progress") is not None for e in node_events
            ), f"{node} 缺少进度"
    assert "task.completed" in event_names
    assert "stream.end" in event_names

    # 6. GET report（§27：Report exists）
    report_resp = client.get(
        f"/api/v1/insight/task/{task_id}/items/{item_id}/report"
    )
    assert report_resp.status_code == 200, report_resp.text
    report = report_resp.json()
    assert report["report_id"]
    assert report["item_id"] == item_id
    assert report["asin"] == "B08N5WRWNW"
    assert report["source_mode"] == "DEMO_DATASET"
    assert report["availability"] in ("SUFFICIENT", "LIMITED", "INSUFFICIENT")
    assert report["limitations"], "limitations 非空"
    cov = report["coverage"]
    assert cov["raw_count"] == cov["valid_count"] + cov["excluded_count"]
    assert cov["raw_count"] > 0
    assert cov["negative_count"] > 0
    assert set(cov["rating_distribution"].keys()) >= {"1", "2", "3", "4", "5"}
    # P0 未评估项（§22/§32：禁止假数字）
    assert report["metrics"]["reform_potential_index"] == {
        "value": None,
        "reason": "NOT_EVALUATED",
        "basis": None,
    }
    assert report["metrics"]["fba_savings_per_unit"]["reason"] == "NOT_EVALUATED"
    assert report["veto_status"] == "NOT_EVALUATED"
    assert report["provenance"]["embedding_mode"] == "demo"

    # 7. clusters >= 1；两栏 proposal 各 >= 1（§27）
    clusters = report["clusters"]
    assert len(clusters) >= 1
    for cluster in clusters:
        assert 1 <= cluster["severity"] <= 5
        assert cluster["frequency"] > 0
        assert cluster["sample_quote"]["text"]
    product_proposals = report["proposals"]["product"]
    packaging_proposals = report["proposals"]["packaging"]
    assert len(product_proposals) >= 1
    assert len(packaging_proposals) >= 1
    cluster_ids = {c["id"] for c in clusters}
    for proposal in product_proposals + packaging_proposals:
        assert set(proposal["target_cluster_ids"]) <= cluster_ids

    # 8. 证据反查：所有 review_id 真实存在于数据库（§27 + §13）
    for cluster in clusters:
        ev = client.get(
            f"/api/v1/insight/task/{task_id}/items/{item_id}/evidence",
            params={"report_id": report["report_id"], "cluster_id": cluster["id"]},
        )
        assert ev.status_code == 200, ev.text
        ev_body = ev.json()
        assert ev_body["total"] >= 1
        assert ev_body["target"] == {"type": "cluster", "id": cluster["id"]}
        assert ev_body["items"], "证据条目非空"

        async def check_review_ids(ids):
            session = factory()
            try:
                found = (
                    await session.execute(
                        select(func.count())
                        .select_from(Review)
                        .where(Review.id.in_([uuid.UUID(i) for i in ids]))
                    )
                ).scalar()
                return found
            finally:
                await session.close()

        referenced = [item["review_id"] for item in ev_body["items"]]
        assert run(check_review_ids(referenced)) == len(referenced)

    proposal_target = packaging_proposals[0]
    ev = client.get(
        f"/api/v1/insight/task/{task_id}/items/{item_id}/evidence",
        params={
            "report_id": report["report_id"],
            "proposal_id": proposal_target["id"],
        },
    )
    assert ev.status_code == 200
    assert ev.json()["target"]["type"] == "proposal"
    assert ev.json()["total"] >= 1

    # 9. 报告持久化断言：DB 里真实存在（非动态拼装）
    async def check_report_row():
        session = factory()
        try:
            result = (
                await session.execute(
                    select(func.count())
                    .select_from(Report)
                    .where(Report.item_id == uuid.UUID(item_id))
                )
            ).scalar()
            event_count = (
                await session.execute(
                    select(func.count())
                    .select_from(TaskEvent)
                    .where(TaskEvent.task_id == uuid.UUID(task_id))
                )
            ).scalar()
            return result, event_count
        finally:
            await session.close()

    report_rows, event_rows = run(check_report_row())
    assert report_rows == 1
    assert event_rows >= 15  # task.updated + 7×(RUNNING+COMPLETED) + item.updated + task.completed

    # 10. 刷新后仍可从 Backend 查询（§36-10）
    snapshot_again = client.get(f"/api/v1/insight/task/{task_id}")
    assert snapshot_again.json()["status"] == "COMPLETED"
    assert snapshot_again.json()["items"][0]["report_id"] == report["report_id"]
    _ = (Task, TaskItem)


@requires_pg
def test_evidence_validation_failure_blocks_publish(e2e, monkeypatch):
    """§26-A：引用不存在 → validation failed → 不 publish、无报告。"""
    client, factory, engine = e2e
    from app.agent.nodes import proposal as proposal_node
    from app.agent.providers.proposal import ProposalDraft

    class BogusProvider:
        name = "bogus"

        async def generate(self, clusters):
            # 引用根本不存在的评论 ID —— 防幻觉门必须拦截
            return [
                ProposalDraft(
                    track_type="BODY_OPTIMIZATION",
                    title_zh="幻觉建议",
                    title_en="Hallucinated proposal",
                    problem="problem",
                    recommendation="recommendation",
                    target_cluster_keys=["cluster_0"],
                    expected_effect="x",
                    cost_level="low",
                    evidence_review_ids=[str(uuid.uuid4())],
                )
            ]

    monkeypatch.setattr(proposal_node, "get_proposal_provider", lambda: BogusProvider())

    created = client.post(
        "/api/v1/insight/task",
        headers={"Idempotency-Key": "e2e-bogus-1"},
        json={"project_id": str(PROJECT_A), "asins": ["B08N5WRWNW"]},
    )
    assert created.status_code == 202
    task_id, item_id = created.json()["task_id"], created.json()["items"][0]["item_id"]

    async def poll():
        session = factory()
        try:
            return await worker_runner.poll_once(session, "e2e-worker-bogus")
        finally:
            await session.close()

    assert run(poll()) is True

    snapshot = client.get(f"/api/v1/insight/task/{task_id}")
    assert snapshot.json()["status"] == "FAILED"
    item = snapshot.json()["items"][0]
    assert item["status"] == "FAILED"
    assert item["error"]["code"] == "NODE_FAILED"

    async def check_no_report():
        session = factory()
        try:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(Report)
                    .where(Report.item_id == uuid.UUID(item_id))
                )
            ).scalar()
        finally:
            await session.close()

    assert run(check_no_report()) == 0
    _ = engine

    # 报告 API：失败任务 → REPORT_NOT_AVAILABLE（§5.1）
    resp = client.get(f"/api/v1/insight/task/{task_id}/items/{item_id}/report")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "REPORT_NOT_AVAILABLE"


@requires_pg
def test_report_not_ready_while_running(e2e):
    """§5.1：执行中未发布 → 409 REPORT_NOT_READY。"""
    client, factory, engine = e2e
    created = client.post(
        "/api/v1/insight/task",
        headers={"Idempotency-Key": "e2e-running-1"},
        json={"project_id": str(PROJECT_A), "asins": ["B08N5WRWNW"]},
    )
    task_id, item_id = created.json()["task_id"], created.json()["items"][0]["item_id"]
    resp = client.get(f"/api/v1/insight/task/{task_id}/items/{item_id}/report")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "REPORT_NOT_READY"
    _ = factory, engine

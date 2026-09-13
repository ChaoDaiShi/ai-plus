"""P0 LangGraph 状态（任务 §4）：强类型 InsightState。

业务事实（快照、评论、片段、簇、建议）以数据库为事实来源，状态只携带
节点间的轻量衔接信息与计数；恢复语义由各节点自行从 DB/ItemNode
output_summary 重建，不依赖内存状态存活。
"""

from typing import Any, TypedDict


class InsightState(TypedDict, total=False):
    # 身份
    task_id: str
    item_id: str
    product_id: str
    asin: str
    marketplace: str
    window: dict[str, str]  # {"start_date", "end_date"} ISO 日期

    # 执行控制
    current_node: str | None
    node_index: int
    progress: int
    stop_reason: str | None  # None / "canceled" / "failed" / "stolen"
    error: str | None

    # 数据计数
    source: str | None  # DataSnapshot.source（demo_dataset / amazon_http）
    snapshot_id: str | None
    raw_count: int
    valid_count: int
    filtered_count: int
    negative_count: int
    embedding_count: int
    embedding_model: str | None

    # 产出（无 ID 草稿，publish 节点落库后获得真实 UUID）
    clusters: list[dict[str, Any]]
    other_cluster_review_count: int
    unclassified_review_count: int
    proposals: list[dict[str, Any]]
    evidence_report: dict[str, Any] | None
    report_id: str | None

    # 溯源（hydration 自上游节点 output_summary，恢复路径必需）
    proposal_provider: str | None
    proposal_version: str | None
    clustering_version: str | None

    warnings: list[str]


def initial_state(
    *, task_id: str, item_id: str, product_id: str, asin: str, marketplace: str,
    window: dict[str, str],
) -> InsightState:
    return {
        "task_id": task_id,
        "item_id": item_id,
        "product_id": product_id,
        "asin": asin,
        "marketplace": marketplace,
        "window": window,
        "current_node": None,
        "node_index": -1,
        "progress": 0,
        "stop_reason": None,
        "error": None,
        "clusters": [],
        "proposals": [],
        "warnings": [],
    }

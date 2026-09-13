"""LangGraph 工作流结构测试（任务 §26-A，离线）：编译、7 节点顺序、条件终止。"""

import asyncio

from app.agent.nodes import NODE_ORDER
from app.agent.workflow import build_p0_workflow


class RecordingContext:
    """鸭子类型上下文：记录 run_node 调用顺序，可注入 stop_reason。"""

    def __init__(self, stop_at: str | None = None):
        self.calls: list[str] = []
        self.stop_at = stop_at

    async def run_node(self, node: str, index: int, state: dict) -> dict:
        self.calls.append(node)
        base = {"current_node": node, "node_index": index, "progress": 0}
        if self.stop_at is not None and node == self.stop_at:
            return {**base, "stop_reason": "canceled"}
        return base


def test_graph_compiles_and_runs_all_seven_nodes_in_order():
    ctx = RecordingContext()
    graph = build_p0_workflow(ctx)  # .compile() 在内部执行
    final = asyncio.run(graph.ainvoke({"stop_reason": None}))
    assert ctx.calls == list(NODE_ORDER)
    assert len(NODE_ORDER) == 7
    _ = final


def test_conditional_edge_stops_graph_on_stop_reason():
    ctx = RecordingContext(stop_at="embedding")
    graph = build_p0_workflow(ctx)
    asyncio.run(graph.ainvoke({"stop_reason": None}))
    assert ctx.calls == ["ingestion", "normalization", "embedding"]


def test_state_preserved_across_nodes():
    seen: dict = {}

    class CapturingContext(RecordingContext):
        async def run_node(self, node, index, state):
            seen[node] = dict(state)
            return await super().run_node(node, index, state)

    graph = build_p0_workflow(CapturingContext())
    asyncio.run(graph.ainvoke({"stop_reason": None, "task_id": "task-1"}))
    # 每个节点都能看到初始状态字段（LangGraph 状态贯通）
    assert all(state.get("task_id") == "task-1" for state in seen.values())

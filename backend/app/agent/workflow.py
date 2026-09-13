"""P0 正式 LangGraph 工作流（任务 §4）。

START → ingestion → normalization → embedding → clustering → proposal →
evidence_validation → publish → END 的线性 StateGraph；条件边在每个节点后
检查 stop_reason（取消/失败/租约丢失）提前终止。节点体由 NodeRunContext
包装：业务执行交给 Service/Provider，持久化与守卫沿用 Worker 既有语义。
"""

from langgraph.graph import END, START, StateGraph

from app.agent.context import NodeRunContext
from app.agent.nodes import NODE_ORDER
from app.agent.state import InsightState


def _route_next(next_node: str):
    def route(state: InsightState) -> str:
        return END if state.get("stop_reason") else next_node

    return route


def build_p0_workflow(ctx: NodeRunContext):
    """按 NodeRunContext 构建并编译 P0 工作流（每个分项一个图实例）。"""
    builder = StateGraph(InsightState)

    def make_node(node: str, index: int):
        async def node_fn(state: InsightState) -> dict:
            return await ctx.run_node(node, index, state)

        return node_fn

    for index, node in enumerate(NODE_ORDER):
        builder.add_node(node, make_node(node, index))
    builder.add_edge(START, NODE_ORDER[0])
    for current, nxt in zip(NODE_ORDER, NODE_ORDER[1:], strict=False):
        builder.add_conditional_edges(current, _route_next(nxt), {nxt: nxt, END: END})
    builder.add_edge(NODE_ORDER[-1], END)
    return builder.compile()

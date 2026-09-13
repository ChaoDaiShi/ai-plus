"""节点注册表 re-export（历史入口保持兼容）。

P0 节点顺序、展示元数据与业务实现的唯一事实来源在
app.agent.nodes / app.agent.nodes.*；本模块仅为 services.tasks 等
既有导入方保留 NODE_ORDER 入口，不再包含任何 stub。
"""

from app.agent.nodes import NODE_DISPLAY, NODE_ORDER, NODE_PROGRESS

__all__ = ["NODE_ORDER", "NODE_DISPLAY", "NODE_PROGRESS"]

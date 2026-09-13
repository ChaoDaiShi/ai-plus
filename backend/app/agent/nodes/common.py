"""业务节点共享工具：节点间衔接数据从 DB/ItemNode output_summary 重建。

恢复语义：节点输入一律重新从数据库加载，不依赖上一节点的内存状态；
上一节点的轻量衔接值（如 snapshot_id）从其 ItemNode.output_summary 读取。
"""

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ItemNode, Product, Task, TaskItem


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class NodeDataError(Exception):
    """节点衔接数据缺失（上游节点产物不可恢复）。"""


async def load_task_window(session: AsyncSession, task_id: uuid.UUID) -> dict[str, str]:
    task = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one()
    return dict(task.input["window_resolved"])


async def load_item_context(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> tuple[TaskItem, Product, dict[str, str]]:
    """返回 (item, product, resolved_window)。"""
    item = (
        await session.execute(
            select(TaskItem).where(
                TaskItem.id == item_id, TaskItem.tenant_id == tenant_id
            )
        )
    ).scalar_one()
    product = (
        await session.execute(select(Product).where(Product.id == item.product_id))
    ).scalar_one()
    window = await load_task_window(session, item.task_id)
    return item, product, window


async def load_node_summary(
    session: AsyncSession, item_id: uuid.UUID, attempt: int, node: str
) -> dict | None:
    """取该 item/attempt 指定节点最新 output_version 的 output_summary。"""
    result = await session.execute(
        select(ItemNode)
        .where(
            ItemNode.item_id == item_id,
            ItemNode.attempt == attempt,
            ItemNode.node == node,
        )
        .order_by(ItemNode.output_version.desc())
    )
    row = result.scalars().first()
    if row is None or row.output_summary is None:
        return None
    return dict(row.output_summary)


def dump_summary(summary: dict) -> dict:
    """output_summary 入库前的 JSON 兼容拷贝（list/dict/标量均 JSON 原生）。"""
    return json.loads(json.dumps(summary, ensure_ascii=False, default=str))

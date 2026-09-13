"""阶段 07 报告溯源字段：LLM 标识与聚类算法版本。

Revision ID: 0004_07_report_provenance — 显式 DDL，只追加，不改历史迁移。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_07_report_provenance"
down_revision: str | None = "0003_04_item_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("llm_model_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "reports",
        sa.Column("clustering_version", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reports", "clustering_version")
    op.drop_column("reports", "llm_model_id")

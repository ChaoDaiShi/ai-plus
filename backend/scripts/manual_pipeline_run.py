"""手动全链路验证脚本（开发用）：POST 任务 → poll_once → 打印报告摘要。"""

import asyncio
import json
import uuid
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings, PROJECT_PRESET_ID, TENANT_PRESET_ID
from app.db.models import Report, Task, TaskItem
from app.services import tasks as task_svc
from app.services import reports as report_svc
from app.worker import runner as worker_runner

ASIN = sys.argv[1] if len(sys.argv) > 1 else "B08N5WRWNW"
KEY = f"manual-{uuid.uuid4().hex[:8]}"


async def main():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    s = factory()
    created = await task_svc.create_task(
        s,
        tenant_id=TENANT_PRESET_ID,
        project_id=PROJECT_PRESET_ID,
        platform="amazon",
        marketplace="US",
        asins=[ASIN],
        window_given=None,
        idempotency_key=KEY,
    )
    print("created:", created["status"], created["items"])
    await s.close()

    poll_session = factory()
    claimed = await worker_runner.poll_once(poll_session, "manual-worker")
    await poll_session.close()
    print("claimed:", claimed)

    s = factory()
    task_id = uuid.UUID(created["task_id"])
    item = (
        await s.execute(select(TaskItem).where(TaskItem.task_id == task_id))
    ).scalars().first()
    print("item status:", item.status, "| error:", item.error)
    if item.status == "COMPLETED":
        report = (
            await s.execute(select(Report).where(Report.item_id == item.id))
        ).scalars().first()
        print("report:", str(report.id)[:8], report.availability)
        task = (
            await s.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        payload = await report_svc.build_report_payload(s, report, task, item)
        cov = payload["coverage"]
        print(
            "coverage: raw=%s valid=%s excluded=%s negative=%s"
            % (cov["raw_count"], cov["valid_count"], cov["excluded_count"], cov["negative_count"])
        )
        print("missing_reasons:", cov["missing_reasons"])
        print("clusters:")
        for c in payload["clusters"]:
            quote = c["sample_quote"]["text"][:70] if c["sample_quote"] else None
            print(
                f"  [{c['category']}] {c['name_zh']} / {c['name_en']} "
                f"freq={c['frequency']} sev={c['severity']} ev={c['evidence_count']}"
            )
            print(f"      quote: {quote}")
        props = payload["proposals"]
        print(
            "proposals product:", len(props["product"]),
            "packaging:", len(props["packaging"]),
        )
        for p in props["product"] + props["packaging"]:
            print(f"  ({p['column']}) {p['title'][:60]} | ev={p['evidence_count']}")
    await s.close()
    await engine.dispose()


asyncio.run(main())

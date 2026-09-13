"""报告与证据路由（api.md §5）。P0 报告与原文证据正式实现。

错误遵循现有 Envelope：REPORT_NOT_READY(409)、REPORT_NOT_AVAILABLE(404)、
NOT_FOUND(404)、INVALID_INPUT(422)。
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id
from app.api.errors import ErrorCode, error_response
from app.db.session import get_session
from app.services import reports as report_svc

router = APIRouter(tags=["insight-report"])

EVIDENCE_MAX_LIMIT = 100
EVIDENCE_DEFAULT_LIMIT = 20


@router.get("/insight/task/{task_id}/items/{item_id}/report")
async def get_report(
    task_id: str,
    item_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    task_uuid = _parse(task_id, "task_id")
    item_uuid = _parse(item_id, "item_id")
    if task_uuid is None or item_uuid is None:
        return task_uuid or item_uuid
    try:
        report, task, item = await report_svc.load_report(
            session, tenant_id, task_uuid, item_uuid
        )
    except report_svc.NotFound as exc:
        return error_response(404, ErrorCode.NOT_FOUND, str(exc))
    except report_svc.ReportNotReady:
        return error_response(
            409, ErrorCode.REPORT_NOT_READY, "执行中尚未发布报告"
        )
    except report_svc.ReportNotAvailable:
        return error_response(
            404, ErrorCode.REPORT_NOT_AVAILABLE, "任务已终结但没有可用报告"
        )
    return await report_svc.build_report_payload(session, report, task, item)


@router.get("/insight/task/{task_id}/items/{item_id}/evidence")
async def get_evidence(
    task_id: str,
    item_id: str,
    report_id: str,
    cluster_id: str | None = None,
    proposal_id: str | None = None,
    cursor: str | None = None,
    limit: int = EVIDENCE_DEFAULT_LIMIT,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    task_uuid = _parse(task_id, "task_id")
    item_uuid = _parse(item_id, "item_id")
    report_uuid = _parse(report_id, "report_id")
    if task_uuid is None or item_uuid is None or report_uuid is None:
        return task_uuid or item_uuid or report_uuid
    if (cluster_id is None) == (proposal_id is None):
        return error_response(
            422, ErrorCode.INVALID_INPUT, "cluster_id 与 proposal_id 必须且只能指定一个"
        )
    cluster_uuid = _parse(cluster_id, "cluster_id") if cluster_id else None
    if cluster_id is not None and cluster_uuid is None:
        return cluster_uuid
    proposal_uuid = _parse(proposal_id, "proposal_id") if proposal_id else None
    if proposal_id is not None and proposal_uuid is None:
        return proposal_uuid
    if limit < 1 or limit > EVIDENCE_MAX_LIMIT:
        return error_response(422, ErrorCode.INVALID_INPUT, f"limit 须为 1–{EVIDENCE_MAX_LIMIT}")
    try:
        report, _task, _item = await report_svc.load_report(
            session, tenant_id, task_uuid, item_uuid
        )
    except report_svc.NotFound as exc:
        return error_response(404, ErrorCode.NOT_FOUND, str(exc))
    except report_svc.ReportNotReady:
        return error_response(409, ErrorCode.REPORT_NOT_READY, "执行中尚未发布报告")
    except report_svc.ReportNotAvailable:
        return error_response(
            404, ErrorCode.REPORT_NOT_AVAILABLE, "任务已终结但没有可用报告"
        )
    if str(report.id) != report_id:
        return error_response(404, ErrorCode.NOT_FOUND, "报告不属于该分项")
    try:
        cursor_uuid = report_svc.decode_cursor(cursor) if cursor else None
    except ValueError:
        return error_response(422, ErrorCode.INVALID_INPUT, "非法分页游标")
    try:
        return await report_svc.build_evidence_page(
            session,
            report,
            cluster_id=cluster_uuid,
            proposal_id=proposal_uuid,
            cursor=cursor_uuid,
            limit=limit,
        )
    except report_svc.NotFound as exc:
        return error_response(404, ErrorCode.NOT_FOUND, str(exc))


def _parse(value: str | None, field: str):
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return error_response(422, ErrorCode.INVALID_INPUT, f"{field} 必须为 UUID")

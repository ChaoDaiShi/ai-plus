"""应用冒烟测试。"""


def test_health_ok(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_report_routes_keep_error_envelope(client) -> None:
    """报告已正式实现：不存在的任务返回 404 Envelope；SSE 校验 UUID（离线）。"""
    import uuid as uuid_mod

    task_id = str(uuid_mod.uuid4())
    item_id = str(uuid_mod.uuid4())
    resp = client.get(f"/api/v1/insight/task/{task_id}/items/{item_id}/report")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
    malformed = client.get("/api/v1/insight/task/not-a-uuid/events?after=0")
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "INVALID_INPUT"

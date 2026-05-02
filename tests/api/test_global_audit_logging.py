import json


async def test_global_audit_writes_metadata_only(async_client, runtime_dir):
    response = await async_client.get("/v1/models")
    assert response.status_code == 200

    logs_dir = runtime_dir / "logs"
    day_dirs = [p for p in logs_dir.iterdir() if p.is_dir()]
    assert day_dirs

    airouter_log = day_dirs[0] / "airouter.log"
    assert airouter_log.exists()
    lines = [line for line in airouter_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines

    event = json.loads(lines[-1])
    assert "path" in event
    assert "method" in event
    assert "status_code" in event
    assert "latency_ms" in event
    # privacy: no prompt/completion payload fields
    assert "messages" not in event
    assert "input" not in event
    assert "response" not in event


async def test_global_audit_creates_module_log_file(async_client, runtime_dir):
    response = await async_client.post(
        "/v1/responses",
        json={"model": "penis_ai_api/gpt-4o-mini", "input": "hello", "stream": False},
    )
    assert response.status_code in (200, 400, 401, 403, 404, 500, 501, 503)

    logs_dir = runtime_dir / "logs"
    day_dirs = [p for p in logs_dir.iterdir() if p.is_dir()]
    assert day_dirs
    module_log = day_dirs[0] / "penis_ai_api.log"
    assert module_log.exists()

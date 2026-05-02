async def test_get_and_update_mcp_audit_settings(async_client, admin_basic_auth_header):
    get_resp = await async_client.get("/api/admin/ui/logs/mcp-audit", headers=admin_basic_auth_header)
    assert get_resp.status_code == 200
    assert "enabled" in get_resp.json()

    put_resp = await async_client.put(
        "/api/admin/ui/logs/mcp-audit",
        json={"enabled": True, "retention_days": 5, "gzip_enabled": True},
        headers=admin_basic_auth_header,
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["settings"]["retention_days"] == 5


async def test_logs_viewer_endpoints(async_client, admin_basic_auth_header, runtime_dir):
    day_dir = runtime_dir / "logs" / "2026-01-01"
    day_dir.mkdir(parents=True, exist_ok=True)
    log_file = day_dir / "mcp.log.gz"
    log_file.write_text("x", encoding="utf-8")

    list_resp = await async_client.get("/api/admin/ui/logs/files", headers=admin_basic_auth_header)
    assert list_resp.status_code == 200
    logs = list_resp.json()["logs"]
    assert any(item["name"] == "2026-01-01" for item in logs)

    dl_resp = await async_client.get("/api/admin/ui/logs/files/2026-01-01/mcp.log.gz", headers=admin_basic_auth_header)
    assert dl_resp.status_code == 200

    del_file_resp = await async_client.delete("/api/admin/ui/logs/files/2026-01-01/mcp.log.gz", headers=admin_basic_auth_header)
    assert del_file_resp.status_code == 200

    del_day_resp = await async_client.delete("/api/admin/ui/logs/files/2026-01-01", headers=admin_basic_auth_header)
    assert del_day_resp.status_code == 200

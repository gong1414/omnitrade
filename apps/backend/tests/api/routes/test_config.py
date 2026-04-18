"""GET /api/v1/config — exposes allow-listed fields only (never SecretStr)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_config_includes_non_secrets(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/v1/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "trading_strategy" in body
    assert "trading_interval_minutes" in body
    assert "environment" in body
    assert "fee_rebate_percent" in body


@pytest.mark.asyncio
async def test_config_never_exposes_secrets(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/v1/config")
    body = resp.json()
    forbidden = {
        "gate_api_key",
        "gate_api_secret",
        "okx_api_key",
        "okx_api_secret",
        "okx_api_passphrase",
        "manual_close_password",
        "llm_api_key",
        "deepseek_api_key",
        "coinglass_api_key",
        "whale_alert_api_key",
        "etherscan_api_key",
        "lunar_crush_api_key",
    }
    assert forbidden.isdisjoint(body.keys())

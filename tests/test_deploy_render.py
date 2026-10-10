# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.deploy_render import trigger_render_deploy

ROOT = Path(__file__).resolve().parents[1]


def test_trigger_rechaza_url_invalida():
    code, msg = trigger_render_deploy(hook_url="https://example.com/hook")
    assert code == 1
    assert "Deploy Hook" in msg


def test_trigger_ok():
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response

    with patch("httpx.Client", return_value=mock_client):
        code, msg = trigger_render_deploy(
            hook_url="https://api.render.com/deploy/srv-test?key=abc",
            clear_cache=True,
        )

    assert code == 0
    assert "202" in msg
    called_url = mock_client.post.call_args[0][0]
    assert "clearCache=true" in called_url


def test_docker_entrypoint_migra_explicitamente():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    entry = (ROOT / "scripts" / "docker_entrypoint.sh").read_text(encoding="utf-8")
    assert "docker_entrypoint.sh" in dockerfile
    assert "AUTO_MIGRATE_ON_STARTUP=false" in dockerfile
    assert "upgrade_company_schema.py --legacy" in entry


def test_render_blueprint_desactiva_auto_migrate():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "AUTO_MIGRATE_ON_STARTUP" in blueprint
    assert 'value: "false"' in blueprint

# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.deploy_render import trigger_render_deploy


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

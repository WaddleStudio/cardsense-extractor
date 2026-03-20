import os
import sys
from unittest.mock import MagicMock, patch

import pytest

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.ingest import fetch_rendered_page


def test_fetch_rendered_page_returns_html_from_cloudflare_api():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "<html><body>Hello</body></html>"}

    with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "test-id", "CLOUDFLARE_API_TOKEN": "test-token"}):
        with patch("extractor.ingest.requests.post", return_value=mock_response) as mock_post:
            html = fetch_rendered_page("https://example.com/page")

    assert html == "<html><body>Hello</body></html>"
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "browser-rendering/content" in call_args[0][0]
    assert call_args[1]["json"]["url"] == "https://example.com/page"


def test_fetch_rendered_page_raises_on_api_error():
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.raise_for_status.side_effect = Exception("403 Forbidden")

    with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "test-id", "CLOUDFLARE_API_TOKEN": "test-token"}):
        with patch("extractor.ingest.requests.post", return_value=mock_response):
            with pytest.raises(Exception):
                fetch_rendered_page("https://example.com/blocked")

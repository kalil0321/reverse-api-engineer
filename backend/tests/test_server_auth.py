"""The sidecar WebSocket handshake must be gated: no drive-by browser pages,
and only clients holding the shared token (in the path) get through."""

from http import HTTPStatus
from unittest.mock import MagicMock

from rae_agent.server import _make_process_request


def _req(path: str, origin: str | None = None):
    request = MagicMock()
    request.path = path
    request.headers = {"Origin": origin} if origin is not None else {}
    return request


class TestHandshakeGate:
    def test_rejects_browser_origin(self):
        gate = _make_process_request("secret")
        conn = MagicMock()
        result = gate(conn, _req("/secret", origin="https://evil.example"))
        conn.respond.assert_called_once()
        assert conn.respond.call_args[0][0] == HTTPStatus.FORBIDDEN
        assert result is conn.respond.return_value

    def test_rejects_wrong_token(self):
        gate = _make_process_request("secret")
        conn = MagicMock()
        result = gate(conn, _req("/wrong"))
        assert conn.respond.call_args[0][0] == HTTPStatus.UNAUTHORIZED
        assert result is conn.respond.return_value

    def test_rejects_missing_token(self):
        gate = _make_process_request("secret")
        conn = MagicMock()
        gate(conn, _req("/"))
        assert conn.respond.call_args[0][0] == HTTPStatus.UNAUTHORIZED

    def test_accepts_valid_token_without_origin(self):
        gate = _make_process_request("secret")
        conn = MagicMock()
        result = gate(conn, _req("/secret"))
        assert result is None
        conn.respond.assert_not_called()

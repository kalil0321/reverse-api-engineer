import math

import pytest

from rae_agent.protocol import (
    AgentEvent,
    ChatRequest,
    FlowSummary,
    ProtocolError,
    TargetLanguage,
    sanitize_session_id,
)


def make_flow_payload(**overrides):
    base = {
        "id": "flow-1",
        "scheme": "https",
        "method": "GET",
        "url": "https://api.example.com/users",
        "requestHeaders": [["User-Agent", "rae"]],
        "responseStatus": 200,
        "responseHeaders": [["Content-Type", "application/json"]],
        "startedAt": 1700000000.0,
    }
    base.update(overrides)
    return base


def test_chat_request_round_trip():
    payload = {
        "type": "chat",
        "id": "abc",
        "message": "Build me a Python client",
        "target": "python",
        "flows": [make_flow_payload()],
        "history": [{"role": "user", "content": "Hi"}],
    }
    request = ChatRequest.from_payload(payload)
    assert request.id == "abc"
    assert request.target is TargetLanguage.PYTHON
    assert len(request.flows) == 1
    assert request.flows[0].method == "GET"
    assert request.history[0] == {"role": "user", "content": "Hi"}


def test_chat_request_default_target():
    payload = {"type": "chat", "message": "hello"}
    request = ChatRequest.from_payload(payload)
    assert request.target is TargetLanguage.PYTHON


def test_chat_request_rejects_unknown_target():
    with pytest.raises(ProtocolError):
        ChatRequest.from_payload({"type": "chat", "target": "rust"})


def test_chat_request_rejects_non_chat_type():
    with pytest.raises(ProtocolError):
        ChatRequest.from_payload({"type": "ping"})


def test_chat_request_accepts_every_registry_language():
    # Anti-drift guard: the panel must accept every language reverse-api's CLI
    # supports, not a hand-picked subset (it used to accept only 3 of 9).
    from reverse_api.utils import OUTPUT_LANGUAGE_EXTENSIONS

    assert len(OUTPUT_LANGUAGE_EXTENSIONS) >= 9
    for value in OUTPUT_LANGUAGE_EXTENSIONS:
        request = ChatRequest.from_payload({"type": "chat", "target": value})
        assert request.target.value == value


def test_chat_request_coerces_history_items_to_strings():
    payload = {
        "type": "chat",
        "history": [{"role": None, "content": 42}],
    }
    request = ChatRequest.from_payload(payload)
    assert request.history == [{"role": "None", "content": "42"}]


def test_flow_summary_rejects_missing_required_fields():
    with pytest.raises(ProtocolError):
        FlowSummary.from_payload({"scheme": "https"})


def test_flow_summary_rejects_non_numeric_finished_at():
    payload = make_flow_payload(finishedAt="later")
    with pytest.raises(ProtocolError):
        FlowSummary.from_payload(payload)


def test_flow_summary_accepts_int_finished_at():
    payload = make_flow_payload(finishedAt=1700001234)
    flow = FlowSummary.from_payload(payload)
    assert math.isclose(flow.finished_at, 1700001234.0)


def test_flow_summary_finished_at_none_is_passthrough():
    payload = make_flow_payload()
    flow = FlowSummary.from_payload(payload)
    assert flow.finished_at is None


def test_flow_summary_coerces_headers_to_strings():
    payload = make_flow_payload(requestHeaders=[["X-Count", 5]])
    flow = FlowSummary.from_payload(payload)
    assert flow.request_headers == [("X-Count", "5")]


def test_assistant_text_event_serialization():
    event = AgentEvent.assistant_text("abc", "hello")
    assert event.to_dict() == {"type": "assistant_text", "id": "abc", "text": "hello"}


def test_tool_use_event_serialization():
    event = AgentEvent.tool_use("abc", "Write", {"file_path": "client.py"})
    assert event.to_dict() == {
        "type": "tool_use",
        "id": "abc",
        "name": "Write",
        "input": {"file_path": "client.py"},
    }


def test_tool_result_event_serialization():
    event = AgentEvent.tool_result("abc", "Write", "ok", False)
    assert event.to_dict() == {
        "type": "tool_result",
        "id": "abc",
        "name": "Write",
        "output": "ok",
        "is_error": False,
    }


def test_file_written_event_serialization():
    event = AgentEvent.file_written("abc", "/tmp/x.py")
    assert event.to_dict() == {"type": "file_written", "id": "abc", "path": "/tmp/x.py"}


def test_error_event_serialization_without_id():
    event = AgentEvent.error(None, "oops")
    assert event.to_dict() == {"type": "error", "message": "oops"}


def test_error_event_serialization_with_id():
    event = AgentEvent.error("abc", "oops")
    assert event.to_dict() == {"type": "error", "message": "oops", "id": "abc"}


def test_complete_event_serialization():
    event = AgentEvent.complete("abc", "/tmp/out", ["client.py", "models.py"])
    payload = event.to_dict()
    assert payload["type"] == "complete"
    assert payload["workdir"] == "/tmp/out"
    assert payload["files"] == ["client.py", "models.py"]


class TestSanitizeSessionId:
    def test_returns_input_when_safe(self):
        assert sanitize_session_id("abc-123_v2.5", "fb") == "abc-123_v2.5"

    def test_falls_back_when_empty(self):
        assert sanitize_session_id("", "fallback") == "fallback"

    def test_falls_back_for_dot_segments(self):
        assert sanitize_session_id(".", "fb") == "fb"
        assert sanitize_session_id("..", "fb") == "fb"

    def test_rejects_path_traversal_backslash(self):
        assert sanitize_session_id("..\\evil", "fb") == "fb"

    def test_rejects_path_traversal_forward_slash(self):
        assert sanitize_session_id("../evil", "fb") == "fb"

    def test_rejects_absolute_path(self):
        assert sanitize_session_id("/etc/passwd", "fb") == "fb"

    def test_rejects_null_byte(self):
        assert sanitize_session_id("ok\x00", "fb") == "fb"

    def test_rejects_special_characters(self):
        assert sanitize_session_id("ok;ls", "fb") == "fb"
        assert sanitize_session_id("ok space", "fb") == "fb"

    def test_truncates_long_input(self):
        result = sanitize_session_id("a" * 500, "fb")
        assert result == "a" * 128

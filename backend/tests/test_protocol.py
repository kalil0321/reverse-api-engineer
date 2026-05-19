import pytest

from rae_agent.protocol import (
    AgentEvent,
    ChatRequest,
    FlowSummary,
    ProtocolError,
    TargetLanguage,
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


def test_flow_summary_rejects_missing_required_fields():
    with pytest.raises(ProtocolError):
        FlowSummary.from_payload({"scheme": "https"})


def test_assistant_text_event_serialization():
    event = AgentEvent.assistant_text("abc", "hello")
    assert event.to_dict() == {"type": "assistant_text", "id": "abc", "text": "hello"}


def test_error_event_serialization_without_id():
    event = AgentEvent.error(None, "oops")
    assert event.to_dict() == {"type": "error", "message": "oops"}


def test_complete_event_serialization():
    event = AgentEvent.complete("abc", "/tmp/out", ["client.py", "models.py"])
    payload = event.to_dict()
    assert payload["type"] == "complete"
    assert payload["workdir"] == "/tmp/out"
    assert payload["files"] == ["client.py", "models.py"]

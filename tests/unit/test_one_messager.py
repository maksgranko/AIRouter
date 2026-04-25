import json

import pytest

from handlers.misc.one_messager import reformat_messages


@pytest.mark.asyncio
async def test_reformat_messages_returns_single_user_message():
    payload = {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
            {"role": "user", "content": "next"},
        ]
    }

    result = await reformat_messages(json.dumps(payload))
    parsed = json.loads(result)
    assert len(parsed["messages"]) == 1
    assert parsed["messages"][0]["role"] == "user"
    assert "<CURRENT_USER_MESSAGE>" in parsed["messages"][0]["content"]


@pytest.mark.asyncio
async def test_reformat_messages_validates_last_message_role():
    payload = {"messages": [{"role": "assistant", "content": "bad"}]}
    with pytest.raises(ValueError):
        await reformat_messages(json.dumps(payload))


@pytest.mark.asyncio
async def test_reformat_messages_handles_multimodal_content():
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"kind": "unknown", "value": 1},
                ],
            },
            {"role": "assistant", "content": "world"},
            {"role": "user", "content": {"text": "next"}},
        ]
    }
    result = await reformat_messages(payload)
    parsed = json.loads(result)
    assert len(parsed["messages"]) == 1
    assert "CURRENT_USER_MESSAGE" in parsed["messages"][0]["content"]


@pytest.mark.asyncio
async def test_reformat_messages_smart_context_zipper(monkeypatch):
    payload = {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
            {"role": "user", "content": "next"},
        ]
    }

    def fake_compress(text, ratio):
        return "COMPRESSED", [("x", "y")]

    monkeypatch.setattr("handlers.misc.one_messager.compress_text_optimized", fake_compress)
    result = await reformat_messages(payload, smart_context_zipper=True)
    parsed = json.loads(result)
    content = parsed["messages"][0]["content"]
    assert "<REPLACING>" in content
    assert "COMPRESSED" in content

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

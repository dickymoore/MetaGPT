import json

import pytest

from metagpt.configs.llm_config import LLMConfig
from metagpt.provider.codex_cli_llm import CodexCliLLM
from metagpt.tools.libs.codex_cli import CodexCli


@pytest.mark.asyncio
async def test_codex_cli_llm_acompletion_text(monkeypatch):
    async def fake_run(self, args, input_data=None, timeout=None, cwd=None, env=None):
        payload = json.loads(input_data)
        last = payload["messages"][-1]["content"]
        events = [
            {"type": "item.completed", "item": {"type": "reasoning", "text": "thinking"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": f"Echo: {last}"}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5, "cached_input_tokens": 0}},
        ]
        return "\n".join(json.dumps(evt) for evt in events)

    monkeypatch.setattr(CodexCli, "run", fake_run, raising=True)

    config = LLMConfig(api_type="codex_cli", cli_default_args=[], cli_completion_args=["exec", "--json", "-"])
    llm = CodexCliLLM(config)

    response = await llm.acompletion_text([{"role": "user", "content": "hello"}])
    assert response == "Echo: hello"


@pytest.mark.asyncio
async def test_codex_cli_llm_plain_text_response(monkeypatch):
    async def fake_run(self, args, input_data=None, timeout=None, cwd=None, env=None):
        return "plain-text"

    monkeypatch.setattr(CodexCli, "run", fake_run, raising=True)

    config = LLMConfig(api_type="codex_cli", cli_default_args=[], cli_completion_args=["exec", "--json", "-"])
    llm = CodexCliLLM(config)

    response = await llm.acompletion([{"role": "user", "content": "ping"}])
    assert response["choices"][0]["message"]["content"] == "plain-text"


@pytest.mark.asyncio
async def test_codex_cli_llm_aask_code(monkeypatch):
    async def fake_run(self, args, input_data=None, timeout=None, cwd=None, env=None):
        return json.dumps({
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "execute",
                                    "arguments": json.dumps({"language": "python", "code": "print('hi')"}),
                                }
                            }
                        ],
                    }
                }
            ]
        })

    monkeypatch.setattr(CodexCli, "run", fake_run, raising=True)

    config = LLMConfig(api_type="codex_cli", cli_default_args=[], cli_completion_args=["exec", "--json", "-"])
    llm = CodexCliLLM(config)

    result = await llm.aask_code([{"role": "user", "content": "write code"}])
    assert result == {"language": "python", "code": "print('hi')"}

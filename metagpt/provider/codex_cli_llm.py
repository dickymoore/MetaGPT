#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Codex CLI backed LLM provider."""
from __future__ import annotations

import json
from typing import Any

from metagpt.configs.llm_config import LLMConfig, LLMType
from metagpt.const import USE_CONFIG_TIMEOUT
from metagpt.logs import logger
from metagpt.provider.base_llm import BaseLLM
from metagpt.provider.llm_provider_registry import register_provider
from metagpt.tools.libs.codex_cli import CodexCli, CodexCliError

_DEFAULT_COMPLETION_ARGS: tuple[str, ...] = ("chat",)


@register_provider(LLMType.CODEX_CLI)
class CodexCliLLM(BaseLLM):
    """LLM adapter that proxies requests through the Codex CLI executable."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.model = config.model or "codex-cli"
        default_args = tuple(config.cli_default_args or ()) or None
        self._cli = CodexCli(executable=config.cli_executable or "codex", default_args=default_args)
        completion_args = tuple(str(arg) for arg in (config.cli_completion_args or _DEFAULT_COMPLETION_ARGS))
        self._completion_args = completion_args
        self._env = config.cli_environment or None

    async def _run_cli(self, messages: list[dict[str, Any]], timeout: int) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        if self.config.max_token:
            payload["max_tokens"] = self.config.max_token

        serialized = json.dumps(payload)
        try:
            output = await self._cli.run(
                args=self._completion_args,
                input_data=serialized,
                timeout=timeout,
                env=self._env,
            )
        except CodexCliError as exc:
            raise ConnectionError(str(exc)) from exc

        text = output.strip()
        if not text:
            raise ConnectionError("Codex CLI returned an empty response")

        data = self._parse_cli_output(text)

        return data

    def _parse_cli_output(self, raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and "choices" in parsed:
            return parsed

        messages: list[str] = []
        reasoning: list[str] = []
        usage: dict[str, Any] | None = None
        jsonl_success = True

        for line in raw.splitlines():
            chunk = line.strip()
            if not chunk:
                continue
            try:
                event = json.loads(chunk)
            except json.JSONDecodeError:
                jsonl_success = False
                break

            etype = event.get("type")
            if etype == "item.completed":
                item = event.get("item", {})
                itype = item.get("type")
                text = item.get("text", "")
                if itype == "agent_message" and text:
                    messages.append(text)
                elif itype == "reasoning" and text:
                    reasoning.append(text)
            elif etype == "turn.completed":
                usage = event.get("usage")

        if jsonl_success and messages:
            content = "\n\n".join(messages).strip()
            payload: dict[str, Any] = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": content,
                        }
                    }
                ]
            }
            if reasoning:
                payload["choices"][0]["message"]["reasoning_content"] = "\n\n".join(reasoning).strip()
            if usage:
                payload["usage"] = usage
            return payload

        logger.debug("Codex CLI response was not machine-parsable; returning raw text")
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": raw.strip(),
                    }
                }
            ]
        }

    async def _achat_completion(self, messages: list[dict[str, Any]], timeout: int = USE_CONFIG_TIMEOUT):
        return await self._run_cli(messages, timeout)

    async def _achat_completion_stream(self, messages: list[dict[str, Any]], timeout: int = USE_CONFIG_TIMEOUT) -> str:
        rsp = await self._run_cli(messages, timeout)
        return self.get_choice_text(rsp)

    async def acompletion(self, messages: list[dict[str, Any]], timeout: int = USE_CONFIG_TIMEOUT):
        return await self._run_cli(messages, timeout)

    async def acompletion_text(self, messages: list[dict[str, Any]], stream: bool = False, timeout: int = USE_CONFIG_TIMEOUT) -> str:
        if stream:
            return await self._achat_completion_stream(messages, timeout)
        rsp = await self._run_cli(messages, timeout)
        return self.get_choice_text(rsp)

    async def aask_code(self, messages, timeout: int = USE_CONFIG_TIMEOUT, **kwargs) -> dict:
        rsp = await self._run_cli(self.format_msg(messages), timeout)
        try:
            return self.get_choice_function_arguments(rsp)
        except Exception:  # noqa: BLE001 - fallback to heuristic parsing
            text = self.get_choice_text(rsp)
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("Codex CLI response does not contain callable arguments") from exc

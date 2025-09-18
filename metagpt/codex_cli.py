#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Codex-compatible command line interface for MetaGPT."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import typer
import yaml

from metagpt.const import CONFIG_ROOT
from metagpt.software_company import DEFAULT_CONFIG, copy_config_to, generate_repo


app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


_DEFAULT_CONFIG_DATA = yaml.safe_load(DEFAULT_CONFIG) or {}

_OVERRIDE_TO_FIELD = {
    "api_key": "api_key",
    "base_url": "base_url",
    "model": "model",
    "temperature": "temperature",
    "top_p": "top_p",
    "max_tokens": "max_token",
}

_LEGACY_KEY_ALIASES: Dict[str, Iterable[str]] = {
    "api_key": ("api_key", "openai_api_key", "key", "token"),
    "base_url": ("base_url", "api_base", "apiBase", "endpoint", "url"),
    "model": ("model", "engine"),
    "temperature": ("temperature", "temp"),
    "top_p": ("top_p", "topp"),
    "max_tokens": ("max_tokens", "max_token", "maxTokens"),
}


def _resolve_prompt(idea: Optional[str], prompt_file: Optional[Path]) -> str:
    if prompt_file is not None:
        try:
            return prompt_file.read_text(encoding="utf-8").strip()
        except OSError as err:
            raise typer.BadParameter(f"Failed to read prompt file: {err}") from err

    if idea and idea != "-":
        return idea

    if idea == "-" or not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return data

    return idea or ""


def _convert_value(field: str, value: Any) -> Any:
    if value is None:
        return None

    try:
        if field in {"temperature", "top_p"}:
            return float(value)
        if field == "max_token":
            return int(value)
        return str(value)
    except (TypeError, ValueError) as err:
        raise typer.BadParameter(f"Invalid value for {field.replace('_', ' ')}: {value!r}") from err


def _is_placeholder(value: Optional[str]) -> bool:
    if value is None:
        return True
    normalized = str(value).strip()
    return normalized in {"", "YOUR_API_KEY"}


def _safe_load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _write_config(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def _ensure_config_file(overrides: Dict[str, Any]) -> bool:
    config_path = CONFIG_ROOT / "config2.yaml"
    config_data = _safe_load_config(config_path)
    need_write = False

    if not config_data:
        config_data = yaml.safe_load(DEFAULT_CONFIG) or {}
        need_write = True

    llm_data = config_data.setdefault("llm", {})
    for key, value in (_DEFAULT_CONFIG_DATA.get("llm", {}) or {}).items():
        llm_data.setdefault(key, value)

    placeholder = _is_placeholder(llm_data.get("api_key"))

    if placeholder and overrides.get("api_key"):
        llm_data["api_key"] = str(overrides["api_key"])
        need_write = True

    if need_write:
        for override_key, override_value in overrides.items():
            field = _OVERRIDE_TO_FIELD.get(override_key)
            if field and override_value is not None:
                llm_data[field] = _convert_value(field, override_value)
        _write_config(config_path, config_data)

    return _is_placeholder(llm_data.get("api_key"))


def _search_dict(data: Any, keys: Iterable[str]) -> Optional[Any]:
    if isinstance(data, dict):
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        for value in data.values():
            result = _search_dict(value, keys)
            if result is not None:
                return result
    return None


def _load_legacy_config(explicit_path: Optional[Path]) -> Dict[str, Any]:
    candidates = []
    env_path = os.environ.get("CODEX_CONFIG_PATH")
    if explicit_path is not None:
        candidates.append(explicit_path)
    if env_path:
        candidates.append(Path(env_path))

    legacy_dirs = [Path.home() / ".codex", Path.home() / ".config" / "codex"]
    legacy_files = ("config.yaml", "config.yml", "config.json")

    for directory in legacy_dirs:
        for filename in legacy_files:
            candidates.append(directory / filename)

    for path in candidates:
        if not path or not path.exists():
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        data: Any
        try:
            if path.suffix.lower() == ".json":
                data = json.loads(text)
            else:
                data = yaml.safe_load(text)
        except (json.JSONDecodeError, yaml.YAMLError):
            continue

        if not isinstance(data, dict):
            continue

        overrides = {}
        for key, aliases in _LEGACY_KEY_ALIASES.items():
            value = _search_dict(data, aliases)
            if value is not None:
                overrides[key] = value
        if overrides:
            return overrides

    return {}


def _collect_overrides(
    api_key: Optional[str],
    api_base: Optional[str],
    model: Optional[str],
    temperature: Optional[float],
    top_p: Optional[float],
    max_tokens: Optional[int],
    legacy_config: Optional[Path],
) -> Dict[str, Any]:
    overrides = _load_legacy_config(legacy_config)

    cli_values = {
        "api_key": api_key,
        "base_url": api_base,
        "model": model,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }

    for key, value in cli_values.items():
        if value is not None:
            overrides[key] = value

    return overrides


def _apply_runtime_overrides(overrides: Dict[str, Any]) -> None:
    if not overrides:
        return

    from pydantic import ValidationError

    try:
        from metagpt.config2 import config
    except ValidationError as err:
        raise typer.BadParameter(str(err)) from err

    llm = config.llm
    for key, value in overrides.items():
        field = _OVERRIDE_TO_FIELD.get(key)
        if field and value is not None:
            setattr(llm, field, _convert_value(field, value))


def _run_codex(
    idea: Optional[str],
    prompt_file: Optional[Path],
    investment: float,
    n_round: int,
    code_review: bool,
    run_tests: bool,
    implement: bool,
    project_name: str,
    inc: bool,
    project_path: str,
    reqa_file: str,
    max_auto_summarize_code: int,
    recover_path: Optional[str],
    init_config: bool,
    api_key: Optional[str],
    api_base: Optional[str],
    model: Optional[str],
    temperature: Optional[float],
    top_p: Optional[float],
    max_tokens: Optional[int],
    legacy_config: Optional[Path],
):
    if init_config:
        copy_config_to()
        return

    prompt = _resolve_prompt(idea, prompt_file)
    if not prompt:
        typer.echo("Missing argument 'IDEA'. Run 'codex --help' for more information.")
        raise typer.Exit(code=1)

    overrides = _collect_overrides(
        api_key=api_key,
        api_base=api_base,
        model=model,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        legacy_config=legacy_config,
    )

    missing_key = _ensure_config_file(overrides)
    if missing_key:
        typer.echo(
            "OpenAI API key is not configured. Provide one via --api-key, the CODEX_API_KEY environment variable,"
            " or update ~/.metagpt/config2.yaml."
        )
        raise typer.Exit(code=1)

    _apply_runtime_overrides(overrides)

    return generate_repo(
        prompt,
        investment,
        n_round,
        code_review,
        run_tests,
        implement,
        project_name,
        inc,
        project_path,
        reqa_file,
        max_auto_summarize_code,
        recover_path,
    )


@app.command("", help="Run MetaGPT using the legacy Codex CLI invocation style.")
def codex(
    idea: Optional[str] = typer.Argument(None, help="Your project brief or prompt."),
    prompt_file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Load the project brief from a file.",
    ),
    investment: float = typer.Option(3.0, help="Budget to allocate to the virtual team."),
    n_round: int = typer.Option(5, help="Maximum number of collaboration rounds."),
    code_review: bool = typer.Option(True, help="Enable peer code review."),
    run_tests: bool = typer.Option(False, help="Run tests produced by the agents."),
    implement: bool = typer.Option(True, help="Allow engineers to implement code."),
    project_name: str = typer.Option("", help="Project name override."),
    inc: bool = typer.Option(False, help="Incremental mode for existing repositories."),
    project_path: str = typer.Option(
        "",
        help="Path to an existing project when using incremental mode.",
    ),
    reqa_file: str = typer.Option("", help="Quality assurance specification file."),
    max_auto_summarize_code: int = typer.Option(
        0,
        help="Maximum number of automatic summarisation passes (0 disables the limit).",
    ),
    recover_path: Optional[str] = typer.Option(
        None,
        help="Resume from a serialized team directory.",
    ),
    init_config: bool = typer.Option(False, help="Initialise the MetaGPT configuration file."),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar=("CODEX_API_KEY", "OPENAI_API_KEY"),
        help="Override the OpenAI API key.",
    ),
    api_base: Optional[str] = typer.Option(
        None,
        "--api-base",
        envvar=("CODEX_API_BASE", "OPENAI_API_BASE"),
        help="Override the OpenAI API base URL.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        envvar=("CODEX_MODEL", "OPENAI_MODEL"),
        help="Select the language model to use.",
    ),
    temperature: Optional[float] = typer.Option(
        None,
        "--temperature",
        envvar=("CODEX_TEMPERATURE", "OPENAI_TEMPERATURE"),
        help="Sampling temperature for the model.",
    ),
    top_p: Optional[float] = typer.Option(
        None,
        "--top-p",
        envvar=("CODEX_TOP_P", "OPENAI_TOP_P"),
        help="Top-p nucleus sampling parameter.",
    ),
    max_tokens: Optional[int] = typer.Option(
        None,
        "--max-tokens",
        envvar=("CODEX_MAX_TOKENS", "OPENAI_MAX_TOKENS"),
        help="Maximum tokens the model may generate.",
    ),
    legacy_config: Optional[Path] = typer.Option(
        None,
        "--legacy-config",
        help="Load Codex CLI settings from a legacy configuration file.",
    ),
):
    return _run_codex(
        idea,
        prompt_file,
        investment,
        n_round,
        code_review,
        run_tests,
        implement,
        project_name,
        inc,
        project_path,
        reqa_file,
        max_auto_summarize_code,
        recover_path,
        init_config,
        api_key,
        api_base,
        model,
        temperature,
        top_p,
        max_tokens,
        legacy_config,
    )


app.command("run", help="Alias for the default Codex command.")(codex)


if __name__ == "__main__":
    app()


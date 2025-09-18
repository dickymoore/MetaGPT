#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for the Codex compatibility CLI."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from metagpt import codex_cli


def _setup_cli_environment(monkeypatch, tmp_path: Path) -> Path:
    config_root = tmp_path / ".metagpt"
    monkeypatch.setattr(codex_cli, "CONFIG_ROOT", config_root)
    monkeypatch.setenv("CODEX_API_KEY", "sk-test-123")
    overrides = []
    monkeypatch.setattr(codex_cli, "_apply_runtime_overrides", lambda values: overrides.append(values.copy()))
    monkeypatch.setattr(codex_cli, "_runtime_override_log", overrides, raising=False)
    return config_root


def test_codex_cli_reads_prompt_file(monkeypatch, tmp_path):
    config_root = _setup_cli_environment(monkeypatch, tmp_path)
    captured = {}

    idea_file = tmp_path / "idea.txt"
    idea_file.write_text("Build a CLI helper", encoding="utf-8")

    def fake_generate_repo(*args, **kwargs):
        captured["args"] = args
        return "project-path"

    monkeypatch.setattr(codex_cli, "generate_repo", fake_generate_repo)

    codex_cli._run_codex(
        idea=None,
        prompt_file=idea_file,
        investment=3.0,
        n_round=5,
        code_review=True,
        run_tests=False,
        implement=True,
        project_name="",
        inc=False,
        project_path="",
        reqa_file="",
        max_auto_summarize_code=0,
        recover_path=None,
        init_config=False,
        api_key=os.environ["CODEX_API_KEY"],
        api_base=None,
        model=None,
        temperature=None,
        top_p=None,
        max_tokens=None,
        legacy_config=None,
    )

    assert captured["args"][0] == "Build a CLI helper"

    config_path = config_root / "config2.yaml"
    assert config_path.exists()
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config_data["llm"]["api_key"] == "sk-test-123"


def test_codex_cli_accepts_stdin(monkeypatch, tmp_path):
    _setup_cli_environment(monkeypatch, tmp_path)

    calls = {}

    def fake_generate_repo(*args, **kwargs):
        calls["idea"] = args[0]
        calls["options"] = args[1:]
        return "workspace"

    monkeypatch.setattr(codex_cli, "generate_repo", fake_generate_repo)

    codex_cli._run_codex(
        idea="Ship a weather CLI",
        prompt_file=None,
        investment=3.0,
        n_round=5,
        code_review=True,
        run_tests=False,
        implement=True,
        project_name="demo",
        inc=False,
        project_path="",
        reqa_file="",
        max_auto_summarize_code=0,
        recover_path=None,
        init_config=False,
        api_key=os.environ["CODEX_API_KEY"],
        api_base=None,
        model=None,
        temperature=None,
        top_p=None,
        max_tokens=None,
        legacy_config=None,
    )

    assert calls["idea"] == "Ship a weather CLI"


def test_codex_cli_legacy_config(monkeypatch, tmp_path):
    config_root = _setup_cli_environment(monkeypatch, tmp_path)
    monkeypatch.delenv("CODEX_API_KEY")

    legacy_config = tmp_path / "codex.yml"
    legacy_config.write_text(
        """
api_key: sk-legacy
model: gpt-test
temperature: 0.25
""",
        encoding="utf-8",
    )

    overrides = {}

    def fake_generate_repo(*args, **kwargs):
        overrides["idea"] = args[0]
        return "workspace"

    monkeypatch.setattr(codex_cli, "generate_repo", fake_generate_repo)

    codex_cli._run_codex(
        idea="New project",
        prompt_file=None,
        investment=3.0,
        n_round=5,
        code_review=True,
        run_tests=False,
        implement=True,
        project_name="",
        inc=False,
        project_path="",
        reqa_file="",
        max_auto_summarize_code=0,
        recover_path=None,
        init_config=False,
        api_key=None,
        api_base=None,
        model=None,
        temperature=None,
        top_p=None,
        max_tokens=None,
        legacy_config=legacy_config,
    )

    assert overrides["idea"] == "New project"

    config_data = yaml.safe_load((config_root / "config2.yaml").read_text(encoding="utf-8"))
    assert config_data["llm"]["api_key"] == "sk-legacy"
    assert config_data["llm"]["model"] == "gpt-test"


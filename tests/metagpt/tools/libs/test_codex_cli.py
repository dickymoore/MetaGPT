import asyncio
from asyncio.subprocess import PIPE, STDOUT

import pytest

from metagpt.tools.libs.codex_cli import CodexCli, CodexCliError


@pytest.mark.asyncio
async def test_codex_cli_run(monkeypatch, tmp_path):
    captured = {}

    class DummyProc:
        returncode = 0

        async def communicate(self, data):
            captured["input"] = data
            return b"codex-output", b""

        def kill(self):
            captured["killed"] = True

        async def wait(self):
            captured["waited"] = True

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return DummyProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    cli = CodexCli()
    output = await cli.run("plan --flag value", input_data="stdin-data", timeout=4.0, cwd=tmp_path, env={"A": "1"})

    assert output == "codex-output"
    assert captured["cmd"][:2] == ("codex", "--yolo")
    assert captured["cmd"][2:] == ("plan", "--flag", "value")
    assert captured["kwargs"]["stdin"] is PIPE
    assert captured["kwargs"]["stdout"] is PIPE
    assert captured["kwargs"]["stderr"] is STDOUT
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    assert captured["kwargs"]["env"] == {"A": "1"}
    assert captured["input"] == b"stdin-data"
    assert "killed" not in captured
    assert "waited" not in captured


@pytest.mark.asyncio
async def test_codex_cli_failure(monkeypatch):
    class DummyProc:
        returncode = 2

        async def communicate(self, data):
            return b"failure", b""

        def kill(self):
            pass

        async def wait(self):
            pass

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return DummyProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    cli = CodexCli()
    with pytest.raises(CodexCliError) as excinfo:
        await cli.run(["status"])

    err = excinfo.value
    assert err.returncode == 2
    assert err.output == "failure"
    assert err.command[0] == "codex"
    assert "--yolo" in err.command


@pytest.mark.asyncio
async def test_codex_cli_timeout(monkeypatch):
    events = {}

    class DummyProc:
        returncode = None

        async def communicate(self, data):
            events["communicate"] = True
            return b"", b""

        def kill(self):
            events["killed"] = True

        async def wait(self):
            events["waited"] = True

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        events["spawned"] = True
        return DummyProc()

    async def fake_wait_for(awaitable, timeout):
        events["timeout"] = timeout
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    cli = CodexCli()
    with pytest.raises(asyncio.TimeoutError):
        await cli.run(timeout=3.5)

    assert events["spawned"]
    assert events["timeout"] == 3.5
    assert events["killed"]
    assert events["waited"]

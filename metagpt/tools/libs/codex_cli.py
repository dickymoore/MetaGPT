#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import contextlib
import shlex
from pathlib import Path
from typing import Iterable, Sequence

from asyncio.subprocess import PIPE, STDOUT

from metagpt.const import DEFAULT_WORKSPACE_ROOT
from metagpt.logs import logger
from metagpt.tools.tool_registry import register_tool


class CodexCliError(RuntimeError):
    """Raised when invoking the Codex CLI fails."""

    def __init__(self, command: Sequence[str], returncode: int, output: str):
        message = f"Codex CLI command '{' '.join(command)}' failed with exit code {returncode}"
        super().__init__(message)
        self.command = tuple(command)
        self.returncode = returncode
        self.output = output


@register_tool(tags=["software development", "codex"])
class CodexCli:
    """A tool that proxies Codex CLI invocations through a subprocess."""

    def __init__(self, executable: str = "codex", default_args: Iterable[str] | None = None):
        self.executable = executable
        self.default_args = tuple(default_args or ("--yolo",))

    async def run(
        self,
        args: Sequence[str] | str | None = None,
        input_data: str | None = None,
        timeout: float | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        """
        Execute the Codex CLI with the provided arguments.

        Args:
            args: Extra CLI arguments passed to Codex, either as a sequence or a shell-style string.
            input_data: Optional stdin payload passed to Codex.
            timeout: Optional timeout in seconds for the Codex invocation.
            cwd: Optional working directory for the Codex process. Defaults to the MetaGPT workspace root.
            env: Optional environment overrides for the subprocess.
        """
        extras: list[str] = []
        if isinstance(args, str) and args.strip():
            extras = shlex.split(args)
        elif isinstance(args, Sequence):
            extras = list(args)

        command = [
            str(self.executable),
            *[str(arg) for arg in self.default_args],
            *[str(arg) for arg in extras],
        ]
        workdir = Path(cwd) if cwd else DEFAULT_WORKSPACE_ROOT
        stdin = PIPE if input_data is not None else None

        logger.debug("Executing Codex CLI: %s (cwd=%s)", " ".join(command), workdir)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=stdin,
            stdout=PIPE,
            stderr=STDOUT,
            cwd=str(workdir),
            env=env,
        )

        payload = None if input_data is None else input_data.encode("utf-8")
        communicate_task = asyncio.create_task(process.communicate(payload))

        try:
            stdout_bytes, _ = await asyncio.wait_for(communicate_task, timeout=timeout)
        except asyncio.TimeoutError:
            communicate_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await communicate_task
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            logger.warning("Codex CLI timed out after %s seconds: %s", timeout, " ".join(command))
            raise

        output = stdout_bytes.decode("utf-8", errors="replace")
        if process.returncode:
            logger.error("Codex CLI exited with code %s: %s", process.returncode, output)
            raise CodexCliError(command=command, returncode=process.returncode, output=output)

        return output

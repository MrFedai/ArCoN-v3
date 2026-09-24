"""The single gate for every external command (CLAUDE.md architecture rule).

Nothing else in ArCoN may call `subprocess`. A runner knows whether the run is
a dry run, logs every call, applies timeouts and adds `sudo` when asked.

* `SystemRunner`  — real execution.
* `DryRunRunner`  — read-only commands still run (detection must see the real
  system); mutating commands are only recorded.
* `FakeRunner`    — tests: scripted results, nothing is executed.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence

log = logging.getLogger("arcon.runner")

DEFAULT_TIMEOUT = 3600  # package installs can be slow; callers pass shorter ones for probes


@dataclass(frozen=True)
class Result:
    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    executed: bool = True  # False when a dry run only recorded the command

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandError(RuntimeError):
    def __init__(self, result: Result):
        self.result = result
        cmd = shlex.join(result.argv)
        super().__init__(f"command failed ({result.returncode}): {cmd}\n{result.stderr.strip()}")


class Runner(Protocol):
    dry_run: bool

    def run(self, argv: Sequence[str], *, sudo: bool = False, mutating: bool = True,
            check: bool = True, input: str | None = None, timeout: float | None = None,
            env: dict[str, str] | None = None, cwd: str | None = None,
            interactive: bool = False) -> Result: ...


def _full_argv(argv: Sequence[str], sudo: bool) -> tuple[str, ...]:
    if not argv:
        raise ValueError("empty command")
    return (("sudo", "--") if sudo else ()) + tuple(str(a) for a in argv)


class SystemRunner:
    dry_run = False

    def run(self, argv, *, sudo=False, mutating=True, check=True, input=None, timeout=None, env=None, cwd=None, interactive=False):
        full = _full_argv(argv, sudo)
        log.info("run%s: %s", " (mutating)" if mutating else "", shlex.join(full))
        try:
            if interactive:  # long package transactions: the user sees progress and prompts
                proc = subprocess.run(full, text=True, timeout=timeout or DEFAULT_TIMEOUT, env=env, cwd=cwd)
                proc.stdout, proc.stderr = "", ""
            else:
                proc = subprocess.run(full, input=input, capture_output=True, text=True,
                                      timeout=timeout or DEFAULT_TIMEOUT, env=env, cwd=cwd)
        except FileNotFoundError:
            result = Result(full, 127, "", f"{full[0]}: command not found")
        except subprocess.TimeoutExpired as exc:
            result = Result(full, 124, exc.stdout or "", f"timeout after {exc.timeout}s")
        else:
            result = Result(full, proc.returncode, proc.stdout, proc.stderr)
        if not result.ok:
            log.warning("exit %s: %s", result.returncode, result.stderr.strip()[:500])
        if check and not result.ok:
            raise CommandError(result)
        return result


class DryRunRunner:
    """Executes read-only probes, records mutating commands without running them."""

    dry_run = True

    def __init__(self, probe: Runner | None = None):
        self._probe = probe or SystemRunner()
        self.planned: list[tuple[str, ...]] = []

    def run(self, argv, *, sudo=False, mutating=True, check=True, input=None, timeout=None, env=None, cwd=None, interactive=False):
        full = _full_argv(argv, sudo)
        if mutating:
            self.planned.append(full)
            log.info("dry-run, not executed: %s", shlex.join(full))
            return Result(full, 0, executed=False)
        return self._probe.run(argv, sudo=sudo, mutating=False, check=check,
                               input=input, timeout=timeout, env=env, cwd=cwd, interactive=interactive)


Handler = Callable[[tuple[str, ...], str | None], Result | int | str]


@dataclass
class FakeRunner:
    """Test double. `responses` maps a command prefix (tuple) to a handler or a
    fixed result; the longest matching prefix wins. Unmatched commands succeed
    with empty output. Every call is recorded in `calls`."""

    dry_run: bool = False
    responses: dict[tuple[str, ...], Handler | Result | int | str] = field(default_factory=dict)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    inputs: list[str | None] = field(default_factory=list)

    def on(self, *prefix: str, result: Handler | Result | int | str = 0) -> "FakeRunner":
        self.responses[tuple(prefix)] = result
        return self

    def run(self, argv, *, sudo=False, mutating=True, check=True, input=None, timeout=None, env=None, cwd=None, interactive=False):
        full = _full_argv(argv, sudo)
        self.calls.append(full)
        self.inputs.append(input)
        cmd = full[2:] if sudo else full
        match = max((p for p in self.responses if cmd[: len(p)] == p), key=len, default=None)
        spec = self.responses.get(match, 0) if match is not None else 0
        if callable(spec) and not isinstance(spec, Result):
            spec = spec(cmd, input)
        if isinstance(spec, Result):
            result = Result(full, spec.returncode, spec.stdout, spec.stderr)
        elif isinstance(spec, int):
            result = Result(full, spec)
        else:
            result = Result(full, 0, str(spec))
        if self.dry_run and mutating:
            result = Result(full, 0, executed=False)
        if check and not result.ok:
            raise CommandError(result)
        return result

"""Subprocess sandbox with wall-clock and memory limits.

Not a security sandbox. Linux `resource.setrlimit` and `SIGKILL`-on-timeout are
the right tool when the caller *also* trusts the harness (local RLVR training,
CI). For untrusted third-party code you still want containers; those are the
`ContainerProvider` layer in OpenEnv, not this module.

The interface is abstract so tests can swap in a `MockSandbox` that replays
deterministic results without actually forking a process — essential for CI
where we cannot count on Verilator/GCC being present.
"""

from __future__ import annotations

import os
import resource
import signal
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence


@dataclass(frozen=True)
class SandboxLimits:
    """Resource ceiling for a single run."""

    wall_seconds: float = 10.0
    cpu_seconds: float = 8.0
    memory_mb: int = 512
    max_output_bytes: int = 4 * 1024 * 1024  # 4 MiB of stdout+stderr, truncated after


@dataclass
class SandboxResult:
    """Outcome of one invocation."""

    returncode: int
    stdout: str
    stderr: str
    wall_seconds: float
    timed_out: bool = False
    oom: bool = False
    killed_signal: Optional[int] = None
    details: Dict[str, str] = field(default_factory=dict)


class Sandbox(ABC):
    """Run an external command. Implementations must guarantee that results
    are safe to feed into a deterministic scoring function."""

    @abstractmethod
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Optional[Dict[str, str]] = None,
        stdin_data: Optional[bytes] = None,
        limits: Optional[SandboxLimits] = None,
    ) -> SandboxResult: ...


class SubprocessSandbox(Sandbox):
    """Default implementation for POSIX. Uses `resource.setrlimit` via a
    pre-exec function and enforces wall-clock by sending SIGKILL to the process
    group when the deadline passes."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Optional[Dict[str, str]] = None,
        stdin_data: Optional[bytes] = None,
        limits: Optional[SandboxLimits] = None,
    ) -> SandboxResult:
        limits = limits or SandboxLimits()
        cwd.mkdir(parents=True, exist_ok=True)

        mem_bytes = limits.memory_mb * 1024 * 1024

        def _preexec() -> None:
            # New process group so we can kill runaway children on timeout.
            os.setsid()
            # Hard CPU-seconds and address-space limits. AS limits are enforced
            # by the kernel on mmap()/brk(); a C++ blob that mallocs in a loop
            # will fail at the syscall rather than OOM the host.
            resource.setrlimit(resource.RLIMIT_CPU, (int(limits.cpu_seconds) + 1,) * 2)
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        start = time.monotonic()
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=_preexec,
        )

        timed_out = False
        try:
            stdout, stderr = proc.communicate(
                input=stdin_data, timeout=limits.wall_seconds
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
        wall = time.monotonic() - start

        # Truncate giant outputs so a rogue `while True: print('x')` does not
        # swamp the observation payload and blow past the LLM context.
        stdout_b = _truncate_bytes(stdout or b"", limits.max_output_bytes)
        stderr_b = _truncate_bytes(stderr or b"", limits.max_output_bytes)

        killed_signal = None
        if proc.returncode is not None and proc.returncode < 0:
            killed_signal = -proc.returncode

        oom = _looks_like_oom(stderr_b, proc.returncode)

        return SandboxResult(
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            wall_seconds=wall,
            timed_out=timed_out,
            oom=oom,
            killed_signal=killed_signal,
        )


def _truncate_bytes(data: bytes, limit: int) -> bytes:
    if len(data) <= limit:
        return data
    return data[:limit] + b"\n[...truncated by sandbox...]\n"


def _looks_like_oom(stderr: bytes, returncode: Optional[int]) -> bool:
    needles = (b"MemoryError", b"std::bad_alloc", b"Cannot allocate memory")
    return returncode == -signal.SIGKILL and any(n in stderr for n in needles) or \
        any(n in stderr for n in needles)


class MockSandbox(Sandbox):
    """Scripted sandbox for tests. Feed it a queue of prebuilt `SandboxResult`s;
    each `run` call pops one and records the argv it was called with."""

    def __init__(self, scripted: Sequence[SandboxResult]) -> None:
        self._queue: List[SandboxResult] = list(scripted)
        self.calls: List[List[str]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Optional[Dict[str, str]] = None,
        stdin_data: Optional[bytes] = None,
        limits: Optional[SandboxLimits] = None,
    ) -> SandboxResult:
        self.calls.append(list(argv))
        if not self._queue:
            raise AssertionError("MockSandbox ran out of scripted results")
        return self._queue.pop(0)

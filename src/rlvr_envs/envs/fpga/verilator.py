"""Thin wrapper around the Verilator CLI.

Two phases per submission:
    1. Lint the user's Verilog on its own (fails fast on syntax errors).
    2. Build and run the simulation with the generated harness and vectors.

We never invoke Verilator directly inside the env code — always through the
`Sandbox` abstraction, so unit tests can feed scripted outputs and adversarial
tests can simulate crashes/OOMs/timeouts.

Verdict parsing lives here too because the harness defines the on-the-wire
format and we want a single place that understands it.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from rlvr_envs.core.sandbox import Sandbox, SandboxLimits, SandboxResult


VERILATOR = shutil.which("verilator") or "verilator"


@dataclass(frozen=True)
class SimReport:
    """Parsed result of running the generated simulation binary."""

    ok: bool
    timed_out: bool
    incorrect_case: Optional[int]
    total_cycles: Optional[int]
    per_case_cycles: List[int]


def lint(
    sandbox: Sandbox,
    source_path: Path,
    *,
    cwd: Path,
    wall_seconds: float = 15.0,
) -> SandboxResult:
    """Run `verilator --lint-only -Wall --top-module dut source.v`."""
    return sandbox.run(
        [
            VERILATOR, "--lint-only",
            # Downgrade stylistic width/unused/fallthrough warnings so the
            # correctness gate only fires on genuine syntax/elaboration errors.
            "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "-Wno-UNUSED",
            "-Wno-DECLFILENAME", "-Wno-CASEINCOMPLETE", "-Wno-CASEX",
            "--top-module", "dut", str(source_path),
        ],
        cwd=cwd,
        limits=SandboxLimits(wall_seconds=wall_seconds, cpu_seconds=wall_seconds),
    )


def build(
    sandbox: Sandbox,
    source_path: Path,
    tb_path: Path,
    *,
    cwd: Path,
    wall_seconds: float = 60.0,
) -> SandboxResult:
    """Translate + compile in one step via `verilator --cc --exe --build`."""
    return sandbox.run(
        [
            VERILATOR,
            "--cc",
            "--exe",
            "--build",
            "-j", "1",
            "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "-Wno-UNUSED",
            "-Wno-DECLFILENAME", "-Wno-CASEINCOMPLETE", "-Wno-CASEX",
            "--top-module", "dut",
            "-CFLAGS", "-O2 -std=c++17 -I..",
            "-Mdir", "obj_dir",
            str(source_path),
            str(tb_path),
        ],
        cwd=cwd,
        limits=SandboxLimits(
            wall_seconds=wall_seconds,
            cpu_seconds=wall_seconds,
            memory_mb=1024,
        ),
    )


def run_sim(
    sandbox: Sandbox,
    *,
    cwd: Path,
    vectors_path: Path,
    wall_seconds: float = 30.0,
) -> SandboxResult:
    """Execute the compiled simulator with the given vectors binary."""
    binary = cwd / "obj_dir" / "Vdut"
    return sandbox.run(
        [str(binary), str(vectors_path)],
        cwd=cwd,
        limits=SandboxLimits(wall_seconds=wall_seconds, cpu_seconds=wall_seconds),
    )


_CASE_RE = re.compile(r"^CASE (\d+) (\d+) 0x[0-9a-fA-F]+$", re.MULTILINE)
_TOTAL_RE = re.compile(r"^TOTAL_CYCLES (\d+)$", re.MULTILINE)
_INCORRECT_RE = re.compile(r"^INCORRECT (\d+)", re.MULTILINE)
_TIMEOUT_RE = re.compile(r"^TIMEOUT (\d+)", re.MULTILINE)


def parse_sim_output(stdout: str) -> SimReport:
    """Turn the harness's structured stdout into a SimReport."""
    incorrect = _INCORRECT_RE.search(stdout)
    timeout = _TIMEOUT_RE.search(stdout)
    total = _TOTAL_RE.search(stdout)
    per_case = [int(m.group(2)) for m in _CASE_RE.finditer(stdout)]
    ok = "\nOK\n" in ("\n" + stdout + "\n") and incorrect is None and timeout is None
    return SimReport(
        ok=ok,
        timed_out=timeout is not None,
        incorrect_case=int(incorrect.group(1)) if incorrect else None,
        total_cycles=int(total.group(1)) if total else None,
        per_case_cycles=per_case,
    )

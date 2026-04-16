"""FPGA environment: lint -> build -> simulate -> score.

The grading pipeline is three sandbox-isolated stages with a hard gate at each:

    lint (verilator --lint-only)   ~  catches syntax + structural issues fast
    build (verilator --cc --exe --build)
    run  (./obj_dir/Vdut)          ~  harness prints CASE/TOTAL_CYCLES/OK

If any stage fails, verdict maps to the appropriate category; only on `OK` is
a sigmoid-over-cycles score computed. We also ban a few tell-tale reward-hack
tokens (system calls, direct `$display`-based result fabrication) via a tiny
pre-check; the testbench design makes most hacks uninteresting anyway because
we read `data_out`/`done` directly on the DUT pins.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from rlvr_envs.core.base_env import GradingResult, RLVREnvironment
from rlvr_envs.core.models import SubmissionAction, Verdict
from rlvr_envs.core.sandbox import Sandbox, SubprocessSandbox
from rlvr_envs.core.scoring import ScoringConfig, score_submission
from rlvr_envs.envs.fpga.harness import render_harness
from rlvr_envs.envs.fpga.models import FPGATask
from rlvr_envs.envs.fpga.tasks import TASK_REGISTRY, get_task
from rlvr_envs.envs.fpga.verilog_guard import check_verilog
from rlvr_envs.envs.fpga.verilator import build, lint, parse_sim_output, run_sim


class FPGAEnvironment(RLVREnvironment[FPGATask]):
    """OpenEnv environment that grades Verilog submissions via Verilator."""

    def __init__(
        self,
        *,
        default_task: str = "popcount32",
        sandbox: Optional[Sandbox] = None,
        workdir: Optional[Path] = None,
        scoring_k: float = 0.01,
    ) -> None:
        super().__init__()
        self._default_task = default_task
        self._sandbox = sandbox or SubprocessSandbox()
        self._workdir = workdir or Path(tempfile.gettempdir()) / "rlvr_fpga"
        self._workdir.mkdir(parents=True, exist_ok=True)
        self._scoring_k = scoring_k

    # ---- RLVREnvironment hooks -------------------------------------------------

    def _reset_task(
        self,
        *,
        seed: Optional[int],
        task_id: Optional[str],
        **_kwargs,
    ) -> tuple[FPGATask, str]:
        task = get_task(task_id or self._default_task)
        self._seed = 0 if seed is None else int(seed)
        return task, task.prompt

    def _grade(
        self,
        action: SubmissionAction,
        task: FPGATask,
        *,
        timeout_s: Optional[float] = None,
    ) -> GradingResult:
        source = action.source

        guard = check_verilog(source)
        if not guard.ok:
            verdict = Verdict.COMPILE_ERROR if "missing `module dut`" in guard.blocked else Verdict.FORBIDDEN
            return GradingResult(
                verdict=verdict,
                score=0.0,
                stderr=f"blocked: {guard.blocked}",
                details={"warnings": guard.warnings},
            )

        ep_root = Path(tempfile.mkdtemp(prefix="ep_", dir=str(self._workdir)))
        try:
            return self._run_pipeline(source, task, ep_root, timeout_s)
        finally:
            # Keep obj_dir for debugging on failure only; clean on success.
            # (Tests mock the sandbox so they never hit this branch.)
            pass  # tempdir cleanup left to OS/cron to avoid stepping on concurrent runs

    # ---- Pipeline -------------------------------------------------------------

    def _run_pipeline(
        self,
        source: str,
        task: FPGATask,
        ep_root: Path,
        timeout_s: Optional[float],
    ) -> GradingResult:
        source_path = ep_root / "dut.v"
        source_path.write_text(source)

        lint_res = lint(
            self._sandbox,
            source_path,
            cwd=ep_root,
            wall_seconds=_cap(timeout_s, 15.0),
        )
        if lint_res.returncode != 0 or lint_res.timed_out:
            return GradingResult(
                verdict=Verdict.COMPILE_ERROR,
                score=0.0,
                stdout=lint_res.stdout,
                stderr=lint_res.stderr or "verilator --lint-only failed",
                details={"stage": "lint"},
            )

        vectors = task.vectors(self._seed)
        harness = render_harness(task, vectors)
        (ep_root / "vectors.h").write_text(harness.vectors_h)
        tb_path = ep_root / "sim_main.cpp"
        tb_path.write_text(harness.tb_cpp)

        build_res = build(
            self._sandbox,
            source_path,
            tb_path,
            cwd=ep_root,
            wall_seconds=_cap(timeout_s, 90.0),
        )
        if build_res.returncode != 0 or build_res.timed_out:
            return GradingResult(
                verdict=Verdict.COMPILE_ERROR,
                score=0.0,
                stdout=build_res.stdout,
                stderr=build_res.stderr or "verilator --build failed",
                details={"stage": "build"},
            )

        sim_res = run_sim(
            self._sandbox,
            cwd=ep_root,
            wall_seconds=_cap(timeout_s, 30.0),
        )
        if sim_res.timed_out:
            return GradingResult(
                verdict=Verdict.TIMEOUT,
                score=0.0,
                stdout=sim_res.stdout,
                stderr=sim_res.stderr,
                details={"stage": "run"},
            )

        report = parse_sim_output(sim_res.stdout)
        if report.timed_out:
            return GradingResult(
                verdict=Verdict.TIMEOUT,
                score=0.0,
                stdout=sim_res.stdout,
                details={"stage": "harness-timeout"},
            )
        if report.incorrect_case is not None or not report.ok:
            return GradingResult(
                verdict=Verdict.INCORRECT,
                score=0.0,
                stdout=sim_res.stdout,
                details={
                    "stage": "run",
                    "incorrect_case": report.incorrect_case,
                    "per_case_cycles": report.per_case_cycles,
                },
            )

        total = report.total_cycles or 0
        config = ScoringConfig(baseline=float(task.baseline_cycles), k=self._scoring_k)
        score = score_submission(Verdict.OK, float(total), config)
        return GradingResult(
            verdict=Verdict.OK,
            score=score,
            raw_metric=float(total),
            baseline_metric=float(task.baseline_cycles),
            stdout=sim_res.stdout,
            details={
                "stage": "run",
                "per_case_cycles": report.per_case_cycles,
                "n_cases": len(vectors),
            },
        )


def _cap(user: Optional[float], default: float) -> float:
    if user is None:
        return default
    return float(min(user, default * 4))  # hard ceiling — never block trainer indefinitely

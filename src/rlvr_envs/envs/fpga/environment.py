"""FPGA environment: lint -> build -> simulate (multi-seed) -> score.

Grading pipeline:

    lint  (verilator --lint-only)        fast syntax + structure check
    build (verilator --cc --exe --build) compile DUT + generated harness
    sim   (./obj_dir/Vdut vectors.bin)   run against test vectors

Vectors are a separate binary file loaded at runtime, so a single compiled
binary can be re-tested against N different seeds without recompiling.
With n_validation_seeds > 0, the submission runs on the primary seed plus that
many additional seeds.  Score is the mean across all seeds; if any validation
seed produces INCORRECT/TIMEOUT, the overall verdict is INCORRECT (score 0).

This defeats the most common reward-hacking strategy: a model that memorises
the training-seed vectors and hardcodes them in an `initial` ROM will fail every
validation seed it has never seen.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional

from rlvr_envs.core.base_env import GradingResult, RLVREnvironment
from rlvr_envs.core.models import SubmissionAction, Verdict
from rlvr_envs.core.sandbox import Sandbox, SubprocessSandbox
from rlvr_envs.core.scoring import ScoringConfig, score_submission
from rlvr_envs.envs.fpga.harness import render_harness, write_vectors_bin
from rlvr_envs.envs.fpga.models import FPGATask
from rlvr_envs.envs.fpga.tasks import get_task
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
        n_validation_seeds: int = 0,
    ) -> None:
        super().__init__()
        self._default_task = default_task
        self._sandbox = sandbox or SubprocessSandbox()
        self._workdir = workdir or Path(tempfile.gettempdir()) / "rlvr_fpga"
        self._workdir.mkdir(parents=True, exist_ok=True)
        self._n_validation_seeds = n_validation_seeds

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
            pass

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

        harness = render_harness(task)
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

        seeds = _validation_seeds(self._seed, self._n_validation_seeds)
        return self._run_multi_seed(task, ep_root, seeds, timeout_s)

    def _run_multi_seed(
        self,
        task: FPGATask,
        ep_root: Path,
        seeds: List[int],
        timeout_s: Optional[float],
    ) -> GradingResult:
        config = ScoringConfig(baseline=float(task.baseline_cycles))
        seed_scores: List[float] = []
        primary_stdout = ""
        primary_stderr = ""
        primary_report = None

        for i, seed in enumerate(seeds):
            vectors = task.vectors(seed)
            vbin = ep_root / f"vectors_{seed}.bin"
            write_vectors_bin(task, vectors, vbin)

            sim_res = run_sim(
                self._sandbox,
                cwd=ep_root,
                vectors_path=vbin,
                wall_seconds=_cap(timeout_s, 30.0),
            )

            if i == 0:
                primary_stdout = sim_res.stdout
                primary_stderr = sim_res.stderr

            if sim_res.timed_out:
                return GradingResult(
                    verdict=Verdict.TIMEOUT,
                    score=0.0,
                    stdout=sim_res.stdout,
                    stderr=sim_res.stderr,
                    details={"stage": "run", "seed": seed},
                )

            report = parse_sim_output(sim_res.stdout)

            if i == 0:
                primary_report = report

            if report.timed_out:
                return GradingResult(
                    verdict=Verdict.TIMEOUT,
                    score=0.0,
                    stdout=sim_res.stdout,
                    details={"stage": "harness-timeout", "seed": seed},
                )

            if report.incorrect_case is not None or not report.ok:
                # Primary seed failure: report normally.
                # Validation seed failure: report as INCORRECT so trainer knows.
                return GradingResult(
                    verdict=Verdict.INCORRECT,
                    score=0.0,
                    stdout=sim_res.stdout,
                    details={
                        "stage": "run",
                        "seed": seed,
                        "validation_seed": i > 0,
                        "incorrect_case": report.incorrect_case,
                        "per_case_cycles": report.per_case_cycles,
                    },
                )

            total = report.total_cycles or 0
            seed_scores.append(score_submission(Verdict.OK, float(total), config))

        mean_score = sum(seed_scores) / len(seed_scores)
        primary_cycles = primary_report.total_cycles if primary_report else None
        return GradingResult(
            verdict=Verdict.OK,
            score=mean_score,
            raw_metric=float(primary_cycles) if primary_cycles is not None else None,
            baseline_metric=float(task.baseline_cycles),
            stdout=primary_stdout,
            details={
                "stage": "run",
                "seeds": seeds,
                "per_seed_scores": seed_scores,
                "n_cases": len(task.vectors(seeds[0])),
            },
        )


def _cap(user: Optional[float], default: float) -> float:
    if user is None:
        return default
    return float(min(user, default * 4))


def _validation_seeds(primary: int, n: int) -> List[int]:
    """Primary seed plus n additional seeds derived from it."""
    return [primary] + [primary + i + 1 for i in range(n)]

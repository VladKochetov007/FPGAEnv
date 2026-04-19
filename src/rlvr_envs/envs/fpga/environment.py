"""FPGA environment: lint -> build -> simulate (multi-seed) -> score."""

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
from rlvr_envs.envs.fpga.parse import parse_submission
from rlvr_envs.envs.fpga.tasks import get_task
from rlvr_envs.envs.fpga.verilog_guard import check_verilog
from rlvr_envs.envs.fpga.verilator import (
    build,
    build_async,
    lint,
    lint_async,
    parse_sim_output,
    run_sim,
    run_sim_async,
)


class FPGAEnvironment(RLVREnvironment[FPGATask]):
    """OpenEnv environment that grades Verilog submissions via Verilator."""

    def __init__(
        self,
        *,
        default_task: str = "popcount32",
        sandbox: Optional[Sandbox] = None,
        workdir: Optional[Path] = None,
        n_validation_seeds: int = 0,
        format_bonus: float = 0.0,
    ) -> None:
        super().__init__()
        self._default_task = default_task
        self._sandbox = sandbox or SubprocessSandbox()
        self._workdir = workdir or Path(tempfile.gettempdir()) / "rlvr_fpga"
        self._workdir.mkdir(parents=True, exist_ok=True)
        self._n_validation_seeds = n_validation_seeds
        self._format_bonus = float(format_bonus)

    def _reset_task(self, *, seed: Optional[int], task_id: Optional[str], **_kwargs) -> tuple[FPGATask, str]:
        task = get_task(task_id or self._default_task)
        self._seed = 0 if seed is None else int(seed)
        return task, task.prompt

    def _grade(self, action: SubmissionAction, task: FPGATask, *, timeout_s: Optional[float] = None) -> GradingResult:
        parsed = parse_submission(action.source)
        source = parsed.source
        format_meta = {"had_think": parsed.had_think, "had_answer": parsed.had_answer}

        guard = check_verilog(source)
        if not guard.ok:
            verdict = Verdict.COMPILE_ERROR if "missing `module dut`" in guard.blocked else Verdict.FORBIDDEN
            return GradingResult(verdict=verdict, score=0.0, stderr=f"blocked: {guard.blocked}", details={"warnings": guard.warnings, **format_meta})

        ep_root = Path(tempfile.mkdtemp(prefix="ep_", dir=str(self._workdir)))
        result = self._run_pipeline(source, task, ep_root, timeout_s)
        if result.verdict == Verdict.OK and self._format_bonus > 0.0 and parsed.had_answer:
            result = _apply_format_bonus(result, self._format_bonus)
        result.details = {**(result.details or {}), **format_meta}
        return result

    async def _grade_async(self, action: SubmissionAction, task: FPGATask, *, timeout_s: Optional[float] = None) -> GradingResult:
        parsed = parse_submission(action.source)
        source = parsed.source
        format_meta = {"had_think": parsed.had_think, "had_answer": parsed.had_answer}

        guard = check_verilog(source)
        if not guard.ok:
            verdict = Verdict.COMPILE_ERROR if "missing `module dut`" in guard.blocked else Verdict.FORBIDDEN
            return GradingResult(verdict=verdict, score=0.0, stderr=f"blocked: {guard.blocked}", details={"warnings": guard.warnings, **format_meta})

        ep_root = Path(tempfile.mkdtemp(prefix="ep_", dir=str(self._workdir)))
        result = await self._run_pipeline_async(source, task, ep_root, timeout_s)
        if result.verdict == Verdict.OK and self._format_bonus > 0.0 and parsed.had_answer:
            result = _apply_format_bonus(result, self._format_bonus)
        result.details = {**(result.details or {}), **format_meta}
        return result

    def _run_pipeline(self, source: str, task: FPGATask, ep_root: Path, timeout_s: Optional[float]) -> GradingResult:
        source_path = ep_root / "dut.v"
        source_path.write_text(source)
        lint_res = lint(self._sandbox, source_path, cwd=ep_root, wall_seconds=_cap(timeout_s, 15.0))
        if lint_res.returncode != 0 or lint_res.timed_out:
            return GradingResult(verdict=Verdict.COMPILE_ERROR, score=0.0, stdout=lint_res.stdout, stderr=lint_res.stderr or "lint failed", details={"stage": "lint"})

        harness = render_harness(task)
        tb_path = ep_root / "sim_main.cpp"
        tb_path.write_text(harness.tb_cpp)
        build_res = build(self._sandbox, source_path, tb_path, cwd=ep_root, wall_seconds=_cap(timeout_s, 90.0))
        if build_res.returncode != 0 or build_res.timed_out:
            return GradingResult(verdict=Verdict.COMPILE_ERROR, score=0.0, stdout=build_res.stdout, stderr=build_res.stderr or "build failed", details={"stage": "build"})

        seeds = _validation_seeds(self._seed, self._n_validation_seeds)
        return self._run_multi_seed(task, ep_root, seeds, timeout_s)

    async def _run_pipeline_async(self, source: str, task: FPGATask, ep_root: Path, timeout_s: Optional[float]) -> GradingResult:
        source_path = ep_root / "dut.v"
        source_path.write_text(source)
        lint_res = await lint_async(self._sandbox, source_path, cwd=ep_root, wall_seconds=_cap(timeout_s, 15.0))
        if lint_res.returncode != 0 or lint_res.timed_out:
            return GradingResult(verdict=Verdict.COMPILE_ERROR, score=0.0, stdout=lint_res.stdout, stderr=lint_res.stderr or "lint failed", details={"stage": "lint"})

        harness = render_harness(task)
        tb_path = ep_root / "sim_main.cpp"
        tb_path.write_text(harness.tb_cpp)
        build_res = await build_async(self._sandbox, source_path, tb_path, cwd=ep_root, wall_seconds=_cap(timeout_s, 90.0))
        if build_res.returncode != 0 or build_res.timed_out:
            return GradingResult(verdict=Verdict.COMPILE_ERROR, score=0.0, stdout=build_res.stdout, stderr=build_res.stderr or "build failed", details={"stage": "build"})

        seeds = _validation_seeds(self._seed, self._n_validation_seeds)
        return await self._run_multi_seed_async(task, ep_root, seeds, timeout_s)

    def _run_multi_seed(self, task: FPGATask, ep_root: Path, seeds: List[int], timeout_s: Optional[float]) -> GradingResult:
        config = ScoringConfig(baseline=float(task.baseline_cycles))
        seed_scores = []
        primary_stdout, primary_report = "", None
        for i, seed in enumerate(seeds):
            vectors = task.vectors(seed)
            vbin = ep_root / f"vectors_{seed}.bin"
            write_vectors_bin(task, vectors, vbin)
            sim_res = run_sim(self._sandbox, cwd=ep_root, vectors_path=vbin, wall_seconds=_cap(timeout_s, 30.0))
            if i == 0: primary_stdout = sim_res.stdout
            if sim_res.timed_out: return GradingResult(verdict=Verdict.TIMEOUT, score=0.0, stdout=sim_res.stdout, details={"stage": "run", "seed": seed})
            report = parse_sim_output(sim_res.stdout)
            if i == 0: primary_report = report
            if report.timed_out: return GradingResult(verdict=Verdict.TIMEOUT, score=0.0, stdout=sim_res.stdout, details={"stage": "harness-timeout", "seed": seed})
            if report.incorrect_case is not None or not report.ok:
                return GradingResult(verdict=Verdict.INCORRECT, score=0.0, stdout=sim_res.stdout, details={"stage": "run", "seed": seed, "validation_seed": i > 0, "incorrect_case": report.incorrect_case})
            seed_scores.append(score_submission(Verdict.OK, float(report.total_cycles or 0), config))
        
        mean_score = sum(seed_scores) / len(seed_scores)
        primary_cycles = primary_report.total_cycles if primary_report else None
        return GradingResult(verdict=Verdict.OK, score=mean_score, raw_metric=float(primary_cycles) if primary_cycles is not None else None, baseline_metric=float(task.baseline_cycles), stdout=primary_stdout, details={"stage": "run", "seeds": seeds, "per_seed_scores": seed_scores})

    async def _run_multi_seed_async(self, task: FPGATask, ep_root: Path, seeds: List[int], timeout_s: Optional[float]) -> GradingResult:
        import asyncio
        config = ScoringConfig(baseline=float(task.baseline_cycles))
        async def _run_one(i: int, seed: int):
            vbin = ep_root / f"vectors_{seed}.bin"
            write_vectors_bin(task, task.vectors(seed), vbin)
            sim_res = await run_sim_async(self._sandbox, cwd=ep_root, vectors_path=vbin, wall_seconds=_cap(timeout_s, 30.0))
            return i, seed, sim_res, parse_sim_output(sim_res.stdout)
        
        raw_results = await asyncio.gather(*[_run_one(i, seed) for i, seed in enumerate(seeds)])
        raw_results.sort(key=lambda x: x[0])
        seed_scores, primary_stdout, primary_report = [], "", None
        for i, seed, sim_res, report in raw_results:
            if i == 0: primary_stdout, primary_report = sim_res.stdout, report
            if sim_res.timed_out or report.timed_out: return GradingResult(verdict=Verdict.TIMEOUT, score=0.0, stdout=sim_res.stdout, details={"stage": "run", "seed": seed, "validation_seed": i > 0})
            if report.incorrect_case is not None or not report.ok:
                return GradingResult(verdict=Verdict.INCORRECT, score=0.0, stdout=sim_res.stdout, details={"stage": "run", "seed": seed, "validation_seed": i > 0, "incorrect_case": report.incorrect_case})
            seed_scores.append(score_submission(Verdict.OK, float(report.total_cycles or 0), config))
        
        mean_score = sum(seed_scores) / len(seed_scores)
        primary_cycles = primary_report.total_cycles if primary_report else None
        return GradingResult(verdict=Verdict.OK, score=mean_score, raw_metric=float(primary_cycles) if primary_cycles is not None else None, baseline_metric=float(task.baseline_cycles), stdout=primary_stdout, details={"stage": "run", "seeds": seeds, "per_seed_scores": seed_scores})


def _cap(user: Optional[float], default: float) -> float:
    return float(min(user, default * 4)) if user is not None else default


def _validation_seeds(primary: int, n: int) -> List[int]:
    return [primary] + [primary + i + 1 for i in range(n)]


def _apply_format_bonus(result: GradingResult, bonus: float) -> GradingResult:
    from dataclasses import replace
    return replace(result, score=min(1.0, result.score + bonus))

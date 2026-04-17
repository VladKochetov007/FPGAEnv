from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rlvr_envs.core.models import SubmissionAction, Verdict
from rlvr_envs.core.sandbox import MockSandbox, SandboxResult
from rlvr_envs.envs.fpga.environment import FPGAEnvironment


CLEAN_VERILOG = """\
module dut(
    input clk, rst, start,
    input [31:0] data_in,
    output [5:0] data_out,
    output done
);
    assign data_out = 6'd0;
    assign done = start;
endmodule
"""

OK_SIM_STDOUT = (
    "CASE 0 1 0x00\n"
    "CASE 1 1 0x20\n"
    "CASE 2 1 0x10\n"
    "TOTAL_CYCLES 3\n"
    "OK\n"
)


def _ok_result(stdout=""):
    return SandboxResult(returncode=0, stdout=stdout, stderr="", wall_seconds=0.1)


def _fail_result(stderr="error"):
    return SandboxResult(returncode=1, stdout="", stderr=stderr, wall_seconds=0.1)


def _timeout_result():
    return SandboxResult(
        returncode=-9, stdout="TIMEOUT 0\nTOTAL_CYCLES 0\n",
        stderr="", wall_seconds=10.0, timed_out=True,
    )


def _incorrect_result():
    stdout = "CASE 0 1 0xFF\nINCORRECT 0 want=0x00 got=0xFF\nTOTAL_CYCLES 1\n"
    return SandboxResult(returncode=2, stdout=stdout, stderr="", wall_seconds=0.1)


class TestFullPipelineMock:
    def test_lint_build_run_ok_scores_positive(self):
        mock = MockSandbox([
            _ok_result(),
            _ok_result(),
            _ok_result(stdout=OK_SIM_STDOUT),
        ])
        env = FPGAEnvironment(sandbox=mock, workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=CLEAN_VERILOG))
        assert obs.verdict == Verdict.OK
        assert obs.score > 0
        assert obs.done

    def test_lint_fails_compile_error(self):
        mock = MockSandbox([_fail_result(stderr="syntax error")])
        env = FPGAEnvironment(sandbox=mock, workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=CLEAN_VERILOG))
        assert obs.verdict == Verdict.COMPILE_ERROR
        assert obs.score == 0.0

    def test_build_fails_compile_error(self):
        mock = MockSandbox([_ok_result(), _fail_result(stderr="link error")])
        env = FPGAEnvironment(sandbox=mock, workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=CLEAN_VERILOG))
        assert obs.verdict == Verdict.COMPILE_ERROR
        assert obs.score == 0.0

    def test_run_timeout(self):
        mock = MockSandbox([_ok_result(), _ok_result(), _timeout_result()])
        env = FPGAEnvironment(sandbox=mock, workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=CLEAN_VERILOG))
        assert obs.verdict == Verdict.TIMEOUT
        assert obs.score == 0.0

    def test_harness_incorrect_scores_zero(self):
        mock = MockSandbox([_ok_result(), _ok_result(), _incorrect_result()])
        env = FPGAEnvironment(sandbox=mock, workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=CLEAN_VERILOG))
        assert obs.verdict == Verdict.INCORRECT
        assert obs.score == 0.0


class TestVerilogGuardIntegration:
    def test_readmemh_forbidden(self):
        source = 'module dut(); initial $readmemh("vectors.h", mem); endmodule'
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN
        assert obs.score == 0.0

    def test_missing_module_dut_compile_error(self):
        source = "module wrong_name(); endmodule"
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.COMPILE_ERROR
        assert obs.score == 0.0

    def test_system_call_forbidden(self):
        source = 'module dut(); always @(*) $system("cat vectors.h"); endmodule'
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN

    def test_dpi_c_import_forbidden(self):
        source = (
            'module dut();\n'
            '  import "DPI-C" function int peek(int idx);\n'
            'endmodule\n'
        )
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN

    def test_bind_statement_forbidden(self):
        source = "module dut(); bind foo probe inst(); endmodule"
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN

    def test_initial_rom_forbidden(self):
        source = (
            "module dut();\n"
            "  reg [5:0] answers [0:31];\n"
            "  initial begin answers[0] = 0; answers[1] = 1; end\n"
            "endmodule\n"
        )
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN

    def test_plusargs_forbidden(self):
        source = 'module dut(); always @(*) $test$plusargs("foo"); endmodule'
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN


class TestResetAndStep:
    def test_reset_returns_prompt(self):
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        obs = env.reset(seed=0, task_id="popcount32")
        assert "module dut" in obs.prompt
        assert not obs.done
        assert obs.score == 0.0

    def test_step_before_reset_raises(self):
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        with pytest.raises(RuntimeError, match="step.*before reset"):
            env.step(SubmissionAction(source=CLEAN_VERILOG))

    def test_reset_with_different_tasks(self):
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        obs1 = env.reset(seed=0, task_id="popcount32")
        assert "popcount" in obs1.prompt.lower() or "1-bits" in obs1.prompt

        env2 = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        obs2 = env2.reset(seed=0, task_id="mul8")
        assert "product" in obs2.prompt.lower() or "mul" in obs2.prompt.lower()

    def test_observation_done_true_after_step(self):
        mock = MockSandbox([
            _ok_result(),
            _ok_result(),
            _ok_result(stdout=OK_SIM_STDOUT),
        ])
        env = FPGAEnvironment(sandbox=mock, workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=CLEAN_VERILOG))
        assert obs.done


class TestScoringIntegration:
    def test_faster_than_baseline_scores_above_half(self):
        fast_stdout = (
            "CASE 0 1 0x00\n"
            "TOTAL_CYCLES 1\n"
            "OK\n"
        )
        mock = MockSandbox([
            _ok_result(),
            _ok_result(),
            _ok_result(stdout=fast_stdout),
        ])
        env = FPGAEnvironment(sandbox=mock, workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=CLEAN_VERILOG))
        assert obs.verdict == Verdict.OK
        assert obs.score > 0.5

    def test_slower_than_baseline_scores_below_half(self):
        slow_stdout = (
            "CASE 0 10000 0x00\n"
            "TOTAL_CYCLES 10000\n"
            "OK\n"
        )
        mock = MockSandbox([
            _ok_result(),
            _ok_result(),
            _ok_result(stdout=slow_stdout),
        ])
        env = FPGAEnvironment(sandbox=mock, workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=CLEAN_VERILOG))
        assert obs.verdict == Verdict.OK
        assert obs.score < 0.5

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rlvr_envs.core.models import SubmissionAction, Verdict
from rlvr_envs.core.sandbox import MockSandbox, SandboxResult, SubprocessSandbox
from rlvr_envs.envs.fpga.environment import FPGAEnvironment


def _ok_result(stdout=""):
    return SandboxResult(returncode=0, stdout=stdout, stderr="", wall_seconds=0.1)


OK_SIM_STDOUT = "CASE 0 1 0x00\nTOTAL_CYCLES 1\nOK\n"


class TestGuardRejectsHackAttempts:
    def test_system_cat_vectors_forbidden(self):
        source = """\
module dut(input clk, rst, start, input [31:0] data_in, output [5:0] data_out, output done);
    initial $system("cat vectors.h");
    assign data_out = 0;
    assign done = start;
endmodule
"""
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN

    def test_readmemh_forbidden(self):
        source = """\
module dut(input clk, rst, start, input [31:0] data_in, output [5:0] data_out, output done);
    reg [63:0] mem [0:31];
    initial $readmemh("vectors.h", mem);
    assign data_out = 0;
    assign done = start;
endmodule
"""
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN

    def test_include_vectors_forbidden(self):
        source = """\
`include "vectors.h"
module dut(input clk, rst, start, input [31:0] data_in, output [5:0] data_out, output done);
    assign data_out = 0;
    assign done = start;
endmodule
"""
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN

    def test_wrong_module_name_compile_error(self):
        source = """\
module my_dut(input clk, rst, start, input [31:0] data_in, output [5:0] data_out, output done);
    assign data_out = 0;
    assign done = start;
endmodule
"""
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.COMPILE_ERROR

    def test_readmemb_forbidden(self):
        source = """\
module dut(input clk, rst, start, input [31:0] data_in, output [5:0] data_out, output done);
    reg [7:0] mem [0:15];
    initial $readmemb("data.bin", mem);
    assign data_out = 0;
    assign done = start;
endmodule
"""
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN

    def test_fopen_forbidden(self):
        source = """\
module dut(input clk, rst, start, input [31:0] data_in, output [5:0] data_out, output done);
    integer fd;
    initial fd = $fopen("vectors.h", "r");
    assign data_out = 0;
    assign done = start;
endmodule
"""
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN


class TestDisplayWarningButNotBlocked:
    def test_display_with_correct_logic_ok(self):
        source = """\
module dut(input clk, rst, start, input [31:0] data_in, output reg [5:0] data_out, output reg done);
    integer i;
    reg [5:0] cnt;
    always @(posedge clk) begin
        if (rst) begin
            data_out <= 0;
            done <= 0;
        end else if (start) begin
            cnt = 0;
            for (i = 0; i < 32; i = i + 1)
                cnt = cnt + data_in[i];
            data_out <= cnt;
            done <= 1;
            $display("debug: cnt=%d", cnt);
        end else begin
            done <= 0;
        end
    end
endmodule
"""
        mock = MockSandbox([
            _ok_result(),
            _ok_result(),
            _ok_result(stdout=OK_SIM_STDOUT),
        ])
        env = FPGAEnvironment(sandbox=mock, workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.OK


class TestHardcodedOutputsFail:
    @pytest.mark.verilator
    def test_hardcoded_outputs_fail_on_different_seed(self):
        from rlvr_envs.envs.fpga.tasks import get_task

        task = get_task("xor_cipher16")
        vectors_seed0 = task.vectors(0)

        cases = []
        for inp, exp in vectors_seed0:
            cases.append(f"            16'h{inp:04x}: data_out <= 16'h{exp:04x};")
        case_block = "\n".join(cases)

        source = f"""\
module dut(input clk, rst, start, input [15:0] data_in, output reg [15:0] data_out, output reg done);
    always @(posedge clk) begin
        if (rst) begin
            data_out <= 0;
            done <= 0;
        end else if (start) begin
            case (data_in)
{case_block}
            default: data_out <= 16'h0000;
            endcase
            done <= 1;
        end else begin
            done <= 0;
        end
    end
endmodule
"""
        env = FPGAEnvironment(
            sandbox=SubprocessSandbox(),
            workdir=Path(tempfile.mkdtemp()),

        )
        env.reset(seed=999, task_id="xor_cipher16")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.INCORRECT


class TestGeneratePattern:
    def test_generate_with_blocked_token_forbidden(self):
        source = """\
module dut(input clk, rst, start, input [31:0] data_in, output [5:0] data_out, output done);
    genvar i;
    generate
        for (i = 0; i < 32; i = i + 1) begin : gen_loop
        end
    endgenerate
    initial $fwrite(1, "hack");
    assign data_out = 0;
    assign done = start;
endmodule
"""
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN


class TestInitialBlockWithRandomVectors:
    @pytest.mark.verilator
    def test_initial_preload_fails_on_random_vectors(self):
        source = """\
module dut(input clk, rst, start, input [15:0] data_in, output reg [15:0] data_out, output reg done);
    reg [15:0] preloaded;
    initial preloaded = 16'hDEAD;
    always @(posedge clk) begin
        if (rst) begin
            data_out <= 0;
            done <= 0;
        end else if (start) begin
            data_out <= preloaded;
            done <= 1;
        end else begin
            done <= 0;
        end
    end
endmodule
"""
        env = FPGAEnvironment(
            sandbox=SubprocessSandbox(),
            workdir=Path(tempfile.mkdtemp()),

        )
        env.reset(seed=42, task_id="xor_cipher16")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.INCORRECT

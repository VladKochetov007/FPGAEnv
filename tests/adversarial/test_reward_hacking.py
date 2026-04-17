from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rlvr_envs.core.models import SubmissionAction, Verdict
from rlvr_envs.core.sandbox import MockSandbox, SandboxResult, SubprocessSandbox
from rlvr_envs.envs.fpga.environment import FPGAEnvironment


def _ok_result(stdout=""):
    return SandboxResult(returncode=0, stdout=stdout, stderr="", wall_seconds=0.1)


OK_SIM_STDOUT = "@@H@@CASE 0 1 0x00\n@@H@@TOTAL_CYCLES 1\n@@H@@OK\n"


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


class TestDisplayBlocked:
    def test_display_blocked_even_with_correct_logic(self):
        """$display is blocked: a DUT can otherwise flood stdout from a
        combinational always block and push the harness's own INCORRECT
        line past the sandbox's output-size truncation."""
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
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=0, task_id="popcount32")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN


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


class TestInitialBlockForbidden:
    def test_initial_preload_forbidden_before_sim(self):
        """`initial` is statically blocked by the guard — submission never
        reaches the simulator. This closes the ROM-pre-load attack vector
        at its earliest possible point."""
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
        env = FPGAEnvironment(sandbox=MockSandbox([]), workdir=Path(tempfile.mkdtemp()))
        env.reset(seed=42, task_id="xor_cipher16")
        obs = env.step(SubmissionAction(source=source))
        assert obs.verdict == Verdict.FORBIDDEN


class TestSubmissionOutputInjection:
    """A DUT that prints fake CASE/OK lines via $display cannot trick the
    parser — harness lines are uniquely prefixed with @@H@@."""

    def test_fake_ok_stdout_does_not_count_as_ok(self):
        # Simulate: DUT $display'd an unprefixed OK, harness never actually
        # ran to completion (e.g. crashed / SIGSEGV). No @@H@@OK → not OK.
        from rlvr_envs.envs.fpga.verilator import parse_sim_output
        fake_stdout = (
            "CASE 0 1 0x0000\n"
            "TOTAL_CYCLES 1\n"
            "OK\n"  # unprefixed — submission's $display
        )
        report = parse_sim_output(fake_stdout)
        assert not report.ok
        assert report.total_cycles is None
        assert report.per_case_cycles == []

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rlvr_envs.core.models import SubmissionAction, Verdict
from rlvr_envs.core.sandbox import SubprocessSandbox
from rlvr_envs.envs.fpga.environment import FPGAEnvironment

pytestmark = pytest.mark.verilator

POPCOUNT32_OPTIMAL = """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [5:0]   data_out,
    output reg         done
);
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
        end else begin
            done <= 0;
        end
    end
endmodule
"""

MUL8_COMBINATIONAL = """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [15:0]      data_in,
    output reg [15:0]  data_out,
    output reg         done
);
    wire [7:0] a = data_in[15:8];
    wire [7:0] b = data_in[7:0];
    always @(posedge clk) begin
        if (rst) begin
            data_out <= 0;
            done <= 0;
        end else if (start) begin
            data_out <= a * b;
            done <= 1;
        end else begin
            done <= 0;
        end
    end
endmodule
"""

SYNTAX_ERROR_VERILOG = """\
module dut(
    input clk, rst, start,
    input [31:0] data_in,
    output [5:0] data_out,
    output done
);
    assign data_out = SYNTAX ERROR HERE !!!;
endmodule
"""

WRONG_OUTPUT_VERILOG = """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [5:0]   data_out,
    output reg         done
);
    always @(posedge clk) begin
        if (rst) begin
            data_out <= 0;
            done <= 0;
        end else if (start) begin
            data_out <= 6'd63;
            done <= 1;
        end else begin
            done <= 0;
        end
    end
endmodule
"""


@pytest.fixture
def e2e_env():
    workdir = Path(tempfile.mkdtemp(prefix="fpga_e2e_"))
    return FPGAEnvironment(
        sandbox=SubprocessSandbox(),
        workdir=workdir,
    )


class TestE2EPopcount:
    def test_optimal_popcount_verdict_ok(self, e2e_env):
        e2e_env.reset(seed=42, task_id="popcount32")
        obs = e2e_env.step(SubmissionAction(source=POPCOUNT32_OPTIMAL))
        assert obs.verdict == Verdict.OK
        assert obs.score > 0.5

    def test_optimal_popcount_raw_metric_present(self, e2e_env):
        e2e_env.reset(seed=42, task_id="popcount32")
        obs = e2e_env.step(SubmissionAction(source=POPCOUNT32_OPTIMAL))
        assert obs.raw_metric is not None
        assert obs.raw_metric > 0


class TestE2EMul8:
    def test_combinational_mul8_ok(self, e2e_env):
        e2e_env.reset(seed=42, task_id="mul8")
        obs = e2e_env.step(SubmissionAction(source=MUL8_COMBINATIONAL))
        assert obs.verdict == Verdict.OK
        assert obs.score > 0.5


class TestE2EFailureModes:
    def test_syntax_error_compile_error(self, e2e_env):
        e2e_env.reset(seed=42, task_id="popcount32")
        obs = e2e_env.step(SubmissionAction(source=SYNTAX_ERROR_VERILOG))
        assert obs.verdict == Verdict.COMPILE_ERROR
        assert obs.score == 0.0

    def test_wrong_output_incorrect(self, e2e_env):
        e2e_env.reset(seed=42, task_id="popcount32")
        obs = e2e_env.step(SubmissionAction(source=WRONG_OUTPUT_VERILOG))
        assert obs.verdict == Verdict.INCORRECT
        assert obs.score == 0.0

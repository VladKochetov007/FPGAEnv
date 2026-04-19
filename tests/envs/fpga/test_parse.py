"""Unit tests for the <think>/<answer> submission parser."""

from __future__ import annotations

import pytest

from rlvr_envs.envs.fpga.parse import parse_submission

_VERILOG = """module dut(
    input clk, rst, start,
    input [7:0] data_in,
    output reg done,
    output reg [7:0] data_out
);
    always @(posedge clk) begin
        if (rst) begin done <= 0; data_out <= 0; end
        else if (start) begin data_out <= data_in; done <= 1; end
        else done <= 0;
    end
endmodule"""

_FULL = f"""<think>
Some reasoning about edge cases and pipeline stages.
</think>
<answer>
```verilog
{_VERILOG}
```
</answer>"""


def test_full_format():
    r = parse_submission(_FULL)
    assert r.had_think
    assert r.had_answer
    assert "module dut" in r.source
    assert "<think>" not in r.source
    assert "<answer>" not in r.source
    assert "```" not in r.source


def test_answer_without_think():
    raw = f"<answer>\n```verilog\n{_VERILOG}\n```\n</answer>"
    r = parse_submission(raw)
    assert not r.had_think
    assert r.had_answer
    assert "module dut" in r.source


def test_empty_think_not_counted():
    raw = f"<think>\n  \n</think>\n<answer>\n```verilog\n{_VERILOG}\n```\n</answer>"
    r = parse_submission(raw)
    assert not r.had_think
    assert r.had_answer


def test_fallback_direct_verilog():
    r = parse_submission(_VERILOG)
    assert r.source == _VERILOG
    assert not r.had_think
    assert not r.had_answer


def test_answer_block_no_fence():
    raw = f"<answer>\n{_VERILOG}\n</answer>"
    r = parse_submission(raw)
    assert r.had_answer
    assert "module dut" in r.source


def test_case_insensitive_tags():
    raw = f"<THINK>\nsome thoughts\n</THINK>\n<ANSWER>\n```verilog\n{_VERILOG}\n```\n</ANSWER>"
    r = parse_submission(raw)
    assert r.had_think
    assert r.had_answer
    assert "module dut" in r.source


def test_plain_fence_without_language():
    raw = f"<answer>\n```\n{_VERILOG}\n```\n</answer>"
    r = parse_submission(raw)
    assert r.had_answer
    assert "module dut" in r.source


def test_extra_text_around_answer_block():
    raw = f"Here is my solution:\n{_FULL}\nHope this helps!"
    r = parse_submission(raw)
    assert r.had_think
    assert r.had_answer
    assert "module dut" in r.source


def test_empty_string():
    r = parse_submission("")
    assert r.source == ""
    assert not r.had_think
    assert not r.had_answer


def test_never_raises():
    for raw in [None if False else "", "garbage", "<<>></>", "```", "<think></think>"]:
        r = parse_submission(raw)
        assert isinstance(r.source, str)


def test_missing_answer_tag_but_fence_present():
    raw = f"<think>\n{_VERILOG}\n</think>\n\n```verilog\n{_VERILOG}_FINAL\n```"
    r = parse_submission(raw)
    assert r.had_think
    assert not r.had_answer
    assert r.source == f"{_VERILOG}_FINAL"


def test_no_tags_but_fence_present():
    raw = f"Here is the code:\n```verilog\n{_VERILOG}\n```"
    r = parse_submission(raw)
    assert not r.had_think
    assert not r.had_answer
    assert r.source == _VERILOG


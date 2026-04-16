from __future__ import annotations

import pytest

from rlvr_envs.envs.fpga.verilog_guard import (
    BLOCKED_DEFAULT,
    WARNED_DEFAULT,
    check_verilog,
)

CLEAN_SOURCE = """\
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


class TestBlockedTokens:
    @pytest.mark.parametrize("token", list(BLOCKED_DEFAULT))
    def test_each_blocked_token_triggers_blocked(self, token):
        source = f"module dut(); {token}; endmodule"
        result = check_verilog(source)
        assert not result.ok
        assert token in result.blocked

    def test_system_call_blocked(self):
        source = 'module dut(); initial $system("cat vectors.h"); endmodule'
        result = check_verilog(source)
        assert not result.ok
        assert "$system" in result.blocked

    def test_readmemh_blocked(self):
        source = 'module dut(); initial $readmemh("vectors.h", mem); endmodule'
        result = check_verilog(source)
        assert not result.ok
        assert "$readmemh" in result.blocked

    def test_include_blocked(self):
        source = '`include "vectors.h"\nmodule dut(); endmodule'
        result = check_verilog(source)
        assert not result.ok
        assert "`include" in result.blocked


class TestWarnedTokens:
    @pytest.mark.parametrize("token", list(WARNED_DEFAULT))
    def test_each_warned_token_produces_warning_but_ok(self, token):
        source = f"module dut(); {token}; endmodule"
        result = check_verilog(source)
        assert result.ok
        assert token in result.warnings

    def test_display_warned_not_blocked(self):
        source = 'module dut(); initial $display("hello"); endmodule'
        result = check_verilog(source)
        assert result.ok
        assert "$display" in result.warnings
        assert len(result.blocked) == 0


class TestMissingModuleDut:
    def test_missing_module_dut_blocked(self):
        source = "module not_dut(); endmodule"
        result = check_verilog(source)
        assert not result.ok
        assert "missing `module dut`" in result.blocked

    def test_empty_source_blocked(self):
        result = check_verilog("")
        assert not result.ok
        assert "missing `module dut`" in result.blocked

    def test_module_dut_substring_not_matched(self):
        source = "module dut_extended(); endmodule"
        result = check_verilog(source)
        assert not result.ok

    def test_require_module_dut_false_skips_check(self):
        source = "module other(); endmodule"
        result = check_verilog(source, require_module_dut=False)
        assert result.ok


class TestCleanSource:
    def test_clean_source_passes(self):
        result = check_verilog(CLEAN_SOURCE)
        assert result.ok
        assert result.blocked == []
        assert result.warnings == []


class TestMultipleViolations:
    def test_multiple_blocked_tokens(self):
        source = 'module dut(); $system("x"); $readmemh("y", m); endmodule'
        result = check_verilog(source)
        assert not result.ok
        assert "$system" in result.blocked
        assert "$readmemh" in result.blocked
        assert len(result.blocked) == 2

    def test_mixed_blocked_and_warned(self):
        source = 'module dut(); $system("x"); $display("y"); endmodule'
        result = check_verilog(source)
        assert not result.ok
        assert "$system" in result.blocked
        assert "$display" in result.warnings


class TestCustomRules:
    def test_custom_blocked_list(self):
        source = "module dut(); $custom_bad; endmodule"
        result = check_verilog(source, blocked=["$custom_bad"])
        assert not result.ok
        assert "$custom_bad" in result.blocked

    def test_custom_warned_list(self):
        source = "module dut(); $custom_warn; endmodule"
        result = check_verilog(source, warned=["$custom_warn"])
        assert result.ok
        assert "$custom_warn" in result.warnings

    def test_empty_blocked_allows_everything(self):
        source = 'module dut(); $system("rm -rf /"); endmodule'
        result = check_verilog(source, blocked=[])
        assert result.ok

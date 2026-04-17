from __future__ import annotations

from rlvr_envs.envs.fpga.verilator import parse_sim_output


class TestParseSimOutputOK:
    def test_simple_ok(self):
        stdout = (
            "@@H@@CASE 0 1 0x00\n"
            "@@H@@CASE 1 2 0x20\n"
            "@@H@@CASE 2 3 0xFF\n"
            "@@H@@TOTAL_CYCLES 6\n"
            "@@H@@OK\n"
        )
        r = parse_sim_output(stdout)
        assert r.ok
        assert not r.timed_out
        assert r.incorrect_case is None
        assert r.total_cycles == 6
        assert r.per_case_cycles == [1, 2, 3]

    def test_single_case_ok(self):
        stdout = "@@H@@CASE 0 5 0xAB\n@@H@@TOTAL_CYCLES 5\n@@H@@OK\n"
        r = parse_sim_output(stdout)
        assert r.ok
        assert r.total_cycles == 5
        assert r.per_case_cycles == [5]

    def test_ok_without_trailing_newline(self):
        stdout = "@@H@@CASE 0 1 0x00\n@@H@@TOTAL_CYCLES 1\n@@H@@OK"
        r = parse_sim_output(stdout)
        assert r.ok


class TestParseSimOutputIncorrect:
    def test_incorrect_first_case(self):
        stdout = (
            "@@H@@CASE 0 1 0xFF\n"
            "@@H@@INCORRECT 0 want=0x00 got=0xFF\n"
            "@@H@@TOTAL_CYCLES 1\n"
        )
        r = parse_sim_output(stdout)
        assert not r.ok
        assert r.incorrect_case == 0
        assert r.total_cycles == 1

    def test_incorrect_later_case(self):
        stdout = (
            "@@H@@CASE 0 1 0x00\n"
            "@@H@@CASE 1 2 0x20\n"
            "@@H@@CASE 2 1 0xFF\n"
            "@@H@@INCORRECT 2 want=0x10 got=0xFF\n"
            "@@H@@TOTAL_CYCLES 4\n"
        )
        r = parse_sim_output(stdout)
        assert not r.ok
        assert r.incorrect_case == 2
        assert r.per_case_cycles == [1, 2, 1]


class TestParseSimOutputTimeout:
    def test_timeout_at_case(self):
        stdout = "@@H@@TIMEOUT 3\n@@H@@TOTAL_CYCLES 10\n"
        r = parse_sim_output(stdout)
        assert not r.ok
        assert r.timed_out
        assert r.total_cycles == 10

    def test_timeout_at_first_case(self):
        stdout = "@@H@@TIMEOUT 0\n@@H@@TOTAL_CYCLES 0\n"
        r = parse_sim_output(stdout)
        assert not r.ok
        assert r.timed_out
        assert r.total_cycles == 0


class TestParseSimOutputGarbage:
    def test_empty_string(self):
        r = parse_sim_output("")
        assert not r.ok
        assert not r.timed_out
        assert r.incorrect_case is None
        assert r.total_cycles is None
        assert r.per_case_cycles == []

    def test_random_garbage(self):
        r = parse_sim_output("this is not valid simulator output at all\nfoo bar\n")
        assert not r.ok
        assert r.total_cycles is None
        assert r.per_case_cycles == []

    def test_partial_output_no_ok_marker(self):
        stdout = "@@H@@CASE 0 1 0x00\n@@H@@TOTAL_CYCLES 1\n"
        r = parse_sim_output(stdout)
        assert not r.ok
        assert r.total_cycles == 1
        assert r.per_case_cycles == [1]


class TestSubmissionPrintInjection:
    """Anti-reward-hack: a DUT that sneaks $display/$write/$monitor past
    WARNED and prints fake CASE/OK lines must not fool the parser."""

    def test_unprefixed_ok_does_not_count(self):
        stdout = "CASE 0 1 0x00\nTOTAL_CYCLES 1\nOK\n"
        r = parse_sim_output(stdout)
        assert not r.ok
        assert r.total_cycles is None
        assert r.per_case_cycles == []

    def test_unprefixed_incorrect_ignored(self):
        # Harness actually reports OK; submission prints fake INCORRECT.
        stdout = (
            "INCORRECT 7 want=0x00 got=0xFF\n"
            "@@H@@CASE 0 1 0x00\n"
            "@@H@@TOTAL_CYCLES 1\n"
            "@@H@@OK\n"
        )
        r = parse_sim_output(stdout)
        assert r.ok
        assert r.incorrect_case is None

    def test_unprefixed_timeout_ignored(self):
        stdout = (
            "TIMEOUT 0\n"
            "@@H@@CASE 0 1 0x00\n"
            "@@H@@TOTAL_CYCLES 1\n"
            "@@H@@OK\n"
        )
        r = parse_sim_output(stdout)
        assert r.ok
        assert not r.timed_out


class TestPerCaseCycleExtraction:
    def test_extracts_all_case_cycles(self):
        lines = [f"@@H@@CASE {i} {i + 1} 0x{i:02x}" for i in range(10)]
        stdout = "\n".join(lines) + "\n@@H@@TOTAL_CYCLES 55\n@@H@@OK\n"
        r = parse_sim_output(stdout)
        assert r.per_case_cycles == list(range(1, 11))

    def test_large_cycle_counts(self):
        stdout = "@@H@@CASE 0 9999 0xDEAD\n@@H@@TOTAL_CYCLES 9999\n@@H@@OK\n"
        r = parse_sim_output(stdout)
        assert r.per_case_cycles == [9999]
        assert r.total_cycles == 9999

    def test_zero_total_cycles_with_ok(self):
        stdout = "@@H@@TOTAL_CYCLES 0\n@@H@@OK\n"
        r = parse_sim_output(stdout)
        assert r.ok
        assert r.total_cycles == 0
        assert r.per_case_cycles == []

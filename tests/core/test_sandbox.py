from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rlvr_envs.core.sandbox import MockSandbox, SandboxLimits, SandboxResult, SubprocessSandbox


class TestMockSandbox:
    def test_pops_results_in_order(self):
        r1 = SandboxResult(returncode=0, stdout="first", stderr="", wall_seconds=0.1)
        r2 = SandboxResult(returncode=1, stdout="second", stderr="", wall_seconds=0.2)
        mock = MockSandbox([r1, r2])

        got1 = mock.run(["cmd1"], cwd=Path("/tmp"))
        got2 = mock.run(["cmd2"], cwd=Path("/tmp"))

        assert got1.stdout == "first"
        assert got2.stdout == "second"

    def test_records_argv(self):
        r = SandboxResult(returncode=0, stdout="", stderr="", wall_seconds=0.0)
        mock = MockSandbox([r, r])

        mock.run(["verilator", "--lint-only", "dut.v"], cwd=Path("/tmp"))
        mock.run(["./obj_dir/Vdut"], cwd=Path("/tmp"))

        assert mock.calls[0] == ["verilator", "--lint-only", "dut.v"]
        assert mock.calls[1] == ["./obj_dir/Vdut"]

    def test_raises_when_exhausted(self):
        mock = MockSandbox([])
        with pytest.raises(AssertionError, match="ran out of scripted results"):
            mock.run(["anything"], cwd=Path("/tmp"))

    def test_raises_after_all_consumed(self):
        r = SandboxResult(returncode=0, stdout="", stderr="", wall_seconds=0.0)
        mock = MockSandbox([r])
        mock.run(["first"], cwd=Path("/tmp"))
        with pytest.raises(AssertionError):
            mock.run(["second"], cwd=Path("/tmp"))

    def test_ignores_env_and_stdin(self):
        r = SandboxResult(returncode=0, stdout="ok", stderr="", wall_seconds=0.0)
        mock = MockSandbox([r])
        got = mock.run(
            ["cmd"],
            cwd=Path("/tmp"),
            env={"FOO": "BAR"},
            stdin_data=b"hello",
            limits=SandboxLimits(wall_seconds=5.0),
        )
        assert got.stdout == "ok"


class TestSubprocessSandbox:
    def test_echo_returns_stdout(self):
        sb = SubprocessSandbox()
        with tempfile.TemporaryDirectory() as d:
            result = sb.run(["echo", "hello"], cwd=Path(d))
        assert result.returncode == 0
        assert "hello" in result.stdout
        assert not result.timed_out

    def test_false_command_nonzero_return(self):
        sb = SubprocessSandbox()
        with tempfile.TemporaryDirectory() as d:
            result = sb.run(["false"], cwd=Path(d))
        assert result.returncode != 0

    def test_timeout_enforcement(self):
        sb = SubprocessSandbox()
        with tempfile.TemporaryDirectory() as d:
            result = sb.run(
                ["sleep", "100"],
                cwd=Path(d),
                limits=SandboxLimits(wall_seconds=0.5, cpu_seconds=1.0),
            )
        assert result.timed_out
        assert result.wall_seconds < 5.0

    def test_captures_stderr(self):
        sb = SubprocessSandbox()
        with tempfile.TemporaryDirectory() as d:
            result = sb.run(["bash", "-c", "echo err >&2"], cwd=Path(d))
        assert "err" in result.stderr

    def test_creates_cwd_if_missing(self):
        sb = SubprocessSandbox()
        parent = Path(tempfile.mkdtemp())
        nested = parent / "a" / "b" / "c"
        result = sb.run(["echo", "ok"], cwd=nested)
        assert result.returncode == 0
        assert nested.is_dir()

    def test_stdin_data_forwarded(self):
        sb = SubprocessSandbox()
        with tempfile.TemporaryDirectory() as d:
            result = sb.run(["cat"], cwd=Path(d), stdin_data=b"ping")
        assert "ping" in result.stdout

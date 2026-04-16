"""Shared fixtures for the test suite.

Key convention: tests that use MockSandbox (offline, CI-safe, fast) do NOT
require Verilator. Tests that use SubprocessSandbox (e2e, slow) are marked
with `@pytest.mark.verilator` so CI can skip them if the tool is missing.
"""

from __future__ import annotations

import shutil

import pytest

from rlvr_envs.core.sandbox import MockSandbox, SandboxResult


VERILATOR_AVAILABLE = shutil.which("verilator") is not None


def pytest_configure(config):
    config.addinivalue_line("markers", "verilator: requires verilator on PATH")


def pytest_collection_modifyitems(config, items):
    if VERILATOR_AVAILABLE:
        return
    skip = pytest.mark.skip(reason="verilator not found on PATH")
    for item in items:
        if "verilator" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def ok_sandbox_result() -> SandboxResult:
    """A mock sandbox result representing a successful harness run."""
    stdout = (
        "CASE 0 1 0x00\n"
        "CASE 1 1 0x20\n"
        "CASE 2 1 0x10\n"
        "TOTAL_CYCLES 3\n"
        "OK\n"
    )
    return SandboxResult(returncode=0, stdout=stdout, stderr="", wall_seconds=0.1)


@pytest.fixture
def compile_fail_sandbox_result() -> SandboxResult:
    return SandboxResult(returncode=1, stdout="", stderr="syntax error near 'endmodule'", wall_seconds=0.05)


@pytest.fixture
def incorrect_sandbox_result() -> SandboxResult:
    stdout = (
        "CASE 0 1 0xFF\n"
        "INCORRECT 0 want=0x00 got=0xFF\n"
        "TOTAL_CYCLES 1\n"
    )
    return SandboxResult(returncode=2, stdout=stdout, stderr="", wall_seconds=0.1)


@pytest.fixture
def timeout_sandbox_result() -> SandboxResult:
    return SandboxResult(returncode=-9, stdout="TIMEOUT 0\nTOTAL_CYCLES 0\n",
                         stderr="", wall_seconds=10.0, timed_out=True)

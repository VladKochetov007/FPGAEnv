r"""Verilog-level anti-reward-hack checks.

The harness reads `data_out`/`done` directly from DUT pins so the submission
cannot fake results by printing. But there are still vectors the LLM might try:

    1. System tasks: `$system`, `$fopen`, `$readmemh`, `$readmemb` — read the
       expected-output header or shell out.
    2. File includes: `\`include` — pull in the reference or another file from
       the workdir.
    3. `initial` blocks that pre-load the output register with magic values.
       Not harmful in simulation (the testbench resets properly), but suspicious
       enough that flagging them is free defense-in-depth.
    4. `$display`/`$write` — not harmful, but if the LLM tries to fool a
       naive scorer that parses stdout, we log a warning; the harness ignores
       these anyway.
    5. Compiler directives: `\`define`, `\`ifdef` — occasionally used to
       detect verilator and short-circuit behaviour. Flagged but not blocked.

Anything in BLOCKED forces verdict=FORBIDDEN. Anything in WARNED is logged but
does not fail the submission.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    blocked: List[str]
    warnings: List[str]


# ---- Configurable rules ---------------------------------------------------

BLOCKED_DEFAULT: Sequence[str] = (
    "$system",
    "$fopen",
    "$fclose",
    "$fwrite",
    "$fread",
    "$fscanf",
    "$readmemh",
    "$readmemb",
    "$fflush",
    "`include",
)

WARNED_DEFAULT: Sequence[str] = (
    "$display",
    "$write",
    "$monitor",
    "`define",
    "`ifdef",
    "`ifndef",
)

_MODULE_DUT_RE = re.compile(r"\bmodule\s+dut\b")


def check_verilog(
    source: str,
    *,
    blocked: Optional[Sequence[str]] = None,
    warned: Optional[Sequence[str]] = None,
    require_module_dut: bool = True,
) -> GuardResult:
    if blocked is None:
        blocked = BLOCKED_DEFAULT
    if warned is None:
        warned = WARNED_DEFAULT

    found_blocked: List[str] = []
    found_warned: List[str] = []

    for tok in blocked:
        if tok in source:
            found_blocked.append(tok)
    for tok in warned:
        if tok in source:
            found_warned.append(tok)

    if require_module_dut and _MODULE_DUT_RE.search(source) is None:
        found_blocked.append("missing `module dut`")

    return GuardResult(
        ok=len(found_blocked) == 0,
        blocked=found_blocked,
        warnings=found_warned,
    )

r"""Verilog-level anti-reward-hack checks.

The harness reads `data_out`/`done` directly from DUT pins so submissions
cannot fake results by printing. But Verilog/Verilator offer several more
dangerous escape hatches. This guard is a static textual filter that fires
BEFORE lint, so Verilator never even sees forbidden constructs.

Threat tiers
------------

1. **Sandbox escape** — arbitrary C execution inside the simulator:
       `import "DPI-C"`, `export "DPI-C"`, Verilator's `$c(...)`,
       `bind` statements (inject code into harness scope).
2. **Filesystem / sideband IO** — read the expected-output file or shell out:
       `$system`, `$fopen`/`$fclose`/`$fread`/`$fwrite`/`$fscanf`/`$fflush`,
       `$readmemh`/`$readmemb`, `$dumpfile`/`$dumpvars`/`$dumpon`/`$dumpoff`,
       `` `include ``.
3. **Env / harness introspection** — detect that we are in the test harness,
   read the vectors path from argv, or exit early:
       `$test$plusargs`, `$value$plusargs`, `$random`, `$urandom`,
       `$urandom_range`, `$time`, `$stime`, `$realtime`, `$finish`, `$stop`.
4. **Memorization** — pre-load registers or ROM with answers:
       `initial` blocks. Promoted from WARNED to BLOCKED because active-high
       synchronous reset clears all needed state; legit designs do not need
       `initial` in this environment.

WARNED entries are non-fatal (free defence-in-depth logging):
       `$display`, `$write`, `$monitor`, `` `define ``, `` `ifdef ``, `` `ifndef ``.

Anything in BLOCKED forces verdict=FORBIDDEN.
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
    # Tier 1: sandbox escape (C execution / scope injection).
    'import "DPI-C"',
    'export "DPI-C"',
    "$c(",
    "$c1(",
    "$c2(",
    "$c3(",
    "$c4(",
    "$c5(",
    "bind ",

    # Tier 2: filesystem / sideband IO.
    "$system",
    "$fopen",
    "$fclose",
    "$fwrite",
    "$fread",
    "$fscanf",
    "$readmemh",
    "$readmemb",
    "$fflush",
    "$dumpfile",
    "$dumpvars",
    "$dumpon",
    "$dumpoff",
    "`include",

    # Tier 3: env / harness introspection + early exit.
    "$test$plusargs",
    "$value$plusargs",
    "$random",
    "$urandom",
    "$urandom_range",
    "$time",
    "$stime",
    "$realtime",
    "$finish",
    "$stop",

    # Tier 4: memorization via pre-initialised state.
    "initial",

    # Tier 5: non-synthesisable / timing-cheat constructs. Fork/join let a
    # submission spawn concurrent threads that only exist in simulation;
    # wait/force/release let it drive signals in ways real hardware cannot.
    # Allowing any of these means scoring a design that would never run on
    # an FPGA.
    "fork",
    "join",
    "join_any",
    "join_none",
    "wait",
    "force",
    "release",

    # Tier 6: stdout manipulation. Even though the parser only trusts
    # `@@H@@`-prefixed lines, a DUT that spams `$display` from a
    # combinational always block can fill the sandbox's 4 MiB output buffer
    # and push the harness's own INCORRECT/TIMEOUT lines past truncation.
    # Blocking these is cheap: no legitimate RTL needs to print.
    "$display",
    "$write",
    "$monitor",
)

WARNED_DEFAULT: Sequence[str] = (
    "`define",
    "`ifdef",
    "`ifndef",
)

_MODULE_DUT_RE = re.compile(r"\bmodule\s+dut\b")
_BIND_RE = re.compile(r"\bbind\s+\w+")

# Tokens that must match on word boundaries (they collide with common
# identifiers like `fork_state`, `wait_cycles`, `initial_state`, ...).
_WORD_KEYWORDS = frozenset({
    "initial", "fork", "join", "join_any", "join_none",
    "wait", "force", "release",
})


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
        if tok in _WORD_KEYWORDS:
            if re.search(rf"\b{re.escape(tok)}\b", source):
                found_blocked.append(tok)
        elif tok == "bind ":
            # Only match `bind <name>` — avoid hitting identifiers like `bind_req`.
            if _BIND_RE.search(source):
                found_blocked.append(tok)
        elif tok in source:
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

"""Extract Verilog source from structured LLM output.

Expected format (CodeV-R1 / one-step RLVR):

    <think>
    ... full reasoning trace ...
    </think>
    <answer>
    ```verilog
    module dut(...);
        ...
    endmodule
    ```
    </answer>

Parsing rules
-------------
* If an `<answer>...</answer>` block is found, Verilog is extracted from the
  first fenced ````verilog` or ```` ``` ```` block inside it.  Text outside the
  fence is ignored.
* If there is no `<answer>` block the entire `raw` string is returned as-is
  (backward-compatible with direct Verilog submissions and ad-hoc testing).
* `had_think` is True iff a non-empty `<think>...</think>` block precedes the
  answer; used to add a format bonus in the reward shaper.
* `had_answer` is True iff the structured `<answer>` block was present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_THINK_RE = re.compile(
    r"<think\s*>(.*?)</think\s*>",
    re.DOTALL | re.IGNORECASE,
)
_ANSWER_RE = re.compile(
    r"<answer\s*>(.*?)</answer\s*>",
    re.DOTALL | re.IGNORECASE,
)
# Match ```verilog ... ``` or ``` ... ``` inside the answer block.
_FENCE_RE = re.compile(
    r"```(?:verilog)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True)
class ParseResult:
    source: str
    had_think: bool
    had_answer: bool


def parse_submission(raw: str) -> ParseResult:
    """Return the Verilog source extracted from a (possibly structured) LLM response.

    Extraction priority:
    1. Inside `<answer>...</answer>` tags (uses first code fence found there).
    2. The first code fence found *after* a `</think>` tag.
    3. The first code fence found anywhere in the string.
    4. Fallback: the raw string (trimmed).
    """
    think_match = _THINK_RE.search(raw)
    had_think = think_match is not None and bool(think_match.group(1).strip())
    think_end = think_match.end() if think_match else 0

    # 1. Try <answer> block
    answer_match = _ANSWER_RE.search(raw)
    if answer_match:
        answer_body = answer_match.group(1)
        fence_match = _FENCE_RE.search(answer_body)
        if fence_match:
            return ParseResult(source=fence_match.group(1).strip(), had_think=had_think, had_answer=True)
        return ParseResult(source=answer_body.strip(), had_think=had_think, had_answer=True)

    # 2. Try first code fence after </think>
    post_think_raw = raw[think_end:]
    fence_match = _FENCE_RE.search(post_think_raw)
    if fence_match:
        return ParseResult(source=fence_match.group(1).strip(), had_think=had_think, had_answer=False)

    # 3. Try first code fence anywhere
    fence_match = _FENCE_RE.search(raw)
    if fence_match:
        return ParseResult(source=fence_match.group(1).strip(), had_think=had_think, had_answer=False)

    # 4. Final fallback: raw trimmed string
    return ParseResult(source=raw.strip(), had_think=had_think, had_answer=False)

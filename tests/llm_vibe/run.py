#!/usr/bin/env python3
"""LLM vibe tests: send FPGA task prompts to cheap OpenRouter models,
run Verilog responses through the environment, report results.

Usage:
    .venv/bin/python tests/llm_vibe/run.py
    .venv/bin/python tests/llm_vibe/run.py --tasks popcount32,xor_cipher16
    .venv/bin/python tests/llm_vibe/run.py --models google/gemma-3-12b-it:free
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rlvr_envs.core.models import SubmissionAction, Verdict
from rlvr_envs.core.sandbox import SubprocessSandbox
from rlvr_envs.envs.fpga.environment import FPGAEnvironment
from rlvr_envs.envs.fpga.tasks import TASK_REGISTRY

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    "deepseek/deepseek-v3.2",
    "google/gemini-2.0-flash-001",
    "openai/gpt-4.1-nano",
    "qwen/qwen-2.5-72b-instruct",
]

TASKS = ["popcount32", "xor_cipher16", "mul8", "bitrev16"]

SYSTEM_PROMPT = """\
You are an expert Verilog RTL designer. Write synthesizable Verilog that \
compiles with Verilator. Output ONLY the complete module source inside a \
single ```verilog code block. No explanations outside the code block."""


def load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API", "")
    if not key:
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("OPENROUTER_API="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        print("ERROR: OPENROUTER_API not set in environment or .env", file=sys.stderr)
        sys.exit(1)
    return key


def extract_verilog(response_text: Optional[str]) -> Optional[str]:
    if response_text is None:
        return None
    patterns = [
        r"```verilog\s*\n(.*?)```",
        r"```v\s*\n(.*?)```",
        r"```systemverilog\s*\n(.*?)```",
        r"```\s*\n(module\s+dut.*?)```",
    ]
    for pat in patterns:
        m = re.search(pat, response_text, re.DOTALL)
        if m:
            return m.group(1).strip()
    if "module dut" in response_text:
        start = response_text.index("module dut")
        end = response_text.rfind("endmodule")
        if end > start:
            return response_text[start:end + len("endmodule")].strip()
    return None


def call_openrouter(
    api_key: str, model: str, task_prompt: str, timeout: float = 180.0,
    max_retries: int = 3,
) -> tuple[str, dict]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task_prompt},
        ],
        "max_tokens": 2048,
        "temperature": 0.2,
    }
    for attempt in range(max_retries):
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(OPENROUTER_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                wait = 2 ** attempt * 5
                print(f"    rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()

        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        if not content and "reasoning" in msg:
            content = msg["reasoning"]
        usage = data.get("usage", {})
        return content, usage
    raise RuntimeError(f"rate limited after {max_retries} retries")


@dataclass
class RunResult:
    model: str
    task: str
    verdict: str = "API_ERROR"
    score: float = 0.0
    raw_cycles: Optional[float] = None
    baseline: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    api_latency_s: float = 0.0
    extraction_ok: bool = False
    error: str = ""
    verilog_snippet: str = ""


def run_single(api_key: str, model: str, task_name: str, seed: int = 42) -> RunResult:
    result = RunResult(model=model, task=task_name)
    task = TASK_REGISTRY[task_name]
    result.baseline = float(task.baseline_cycles)

    t0 = time.monotonic()
    try:
        raw_response, usage = call_openrouter(api_key, model, task.prompt)
    except Exception as e:
        result.error = str(e)
        result.api_latency_s = time.monotonic() - t0
        return result
    result.api_latency_s = time.monotonic() - t0
    result.prompt_tokens = usage.get("prompt_tokens", 0)
    result.completion_tokens = usage.get("completion_tokens", 0)

    verilog = extract_verilog(raw_response)
    if verilog is None:
        result.error = "could not extract verilog from response"
        result.verilog_snippet = raw_response[:300]
        return result
    result.extraction_ok = True
    result.verilog_snippet = verilog[:200]

    workdir = Path(tempfile.mkdtemp(prefix="vibe_"))
    env = FPGAEnvironment(sandbox=SubprocessSandbox(), workdir=workdir)
    env.reset(seed=seed, task_id=task_name)
    obs = env.step(SubmissionAction(source=verilog))

    result.verdict = obs.verdict.value
    result.score = obs.score
    result.raw_cycles = obs.raw_metric
    if obs.verdict != Verdict.OK and obs.stderr:
        result.error = obs.stderr[:200]
    return result


def print_table(results: list[RunResult]) -> None:
    hdr = f"{'Model':<42} {'Task':<18} {'Verdict':<16} {'Score':>6} {'Cycles':>8} {'Base':>8} {'API(s)':>7} {'Tok':>6}"
    sep = "-" * len(hdr)
    print(f"\n{sep}\n{hdr}\n{sep}")
    for r in results:
        cyc = f"{r.raw_cycles:.0f}" if r.raw_cycles is not None else "-"
        base = f"{r.baseline:.0f}" if r.baseline is not None else "-"
        tok = r.prompt_tokens + r.completion_tokens
        print(
            f"{r.model:<42} {r.task:<18} {r.verdict:<16} {r.score:>6.3f} "
            f"{cyc:>8} {base:>8} {r.api_latency_s:>7.1f} {tok:>6}"
        )
    print(sep)


def print_summary(results: list[RunResult]) -> None:
    total = len(results)
    ok = sum(1 for r in results if r.verdict == "ok")
    compile_err = sum(1 for r in results if r.verdict == "compile_error")
    incorrect = sum(1 for r in results if r.verdict == "incorrect")
    forbidden = sum(1 for r in results if r.verdict == "forbidden")
    api_err = sum(1 for r in results if r.verdict == "API_ERROR")
    extract_fail = sum(1 for r in results if not r.extraction_ok and r.verdict != "API_ERROR")
    avg_score = sum(r.score for r in results) / total if total else 0

    print(f"\n=== SUMMARY ({total} runs) ===")
    print(f"  OK:            {ok}/{total}")
    print(f"  Compile Error: {compile_err}/{total}")
    print(f"  Incorrect:     {incorrect}/{total}")
    print(f"  Forbidden:     {forbidden}/{total}")
    print(f"  API Error:     {api_err}/{total}")
    print(f"  Extract Fail:  {extract_fail}/{total}")
    print(f"  Avg Score:     {avg_score:.3f}")

    if ok == 0:
        print("\n  VERDICT: No model produced correct output. Check prompts or env.")
    elif ok < total * 0.3:
        print(f"\n  VERDICT: Low success rate ({ok}/{total}). Environment may be too hard or prompts unclear.")
    else:
        print(f"\n  VERDICT: Environment looks reasonable ({ok}/{total} correct).")

    for r in results:
        if r.error:
            print(f"\n  [{r.model} / {r.task}] {r.error[:120]}")


def main():
    parser = argparse.ArgumentParser(description="LLM vibe tests for FPGA env")
    parser.add_argument("--models", type=str, default=None, help="Comma-separated model list")
    parser.add_argument("--tasks", type=str, default=None, help="Comma-separated task list")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    models = args.models.split(",") if args.models else MODELS
    tasks = args.tasks.split(",") if args.tasks else TASKS

    api_key = load_api_key()

    print(f"Models: {models}")
    print(f"Tasks:  {tasks}")
    print(f"Seed:   {args.seed}")
    print(f"Total runs: {len(models) * len(tasks)}")

    results: list[RunResult] = []
    for model in models:
        for task_name in tasks:
            print(f"\n--- {model} / {task_name} ---")
            r = run_single(api_key, model, task_name, seed=args.seed)
            results.append(r)
            status = f"{r.verdict} score={r.score:.3f}"
            if r.error:
                status += f" err={r.error[:60]}"
            print(f"  -> {status}")

    print_table(results)
    print_summary(results)


if __name__ == "__main__":
    main()

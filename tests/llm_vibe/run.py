#!/usr/bin/env python3
"""LLM vibe tests: send FPGA task prompts to cheap OpenRouter models,
run Verilog responses through the environment, report results.

Usage:
    .venv/bin/python tests/llm_vibe/run.py
    .venv/bin/python tests/llm_vibe/run.py --tasks popcount32,xor_cipher16
    .venv/bin/python tests/llm_vibe/run.py --models anthropic/claude-sonnet-4.6
    .venv/bin/python tests/llm_vibe/run.py --concurrency 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rlvr_envs.core.models import SubmissionAction, Verdict
from rlvr_envs.core.sandbox import SubprocessSandbox
from rlvr_envs.envs.fpga.environment import FPGAEnvironment
from rlvr_envs.envs.fpga.parse import parse_submission
from rlvr_envs.envs.fpga.tasks import TASK_REGISTRY

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"

MODELS = [
    "deepseek/deepseek-v3.2",
    "google/gemini-2.0-flash-001",
    "openai/gpt-4.1-nano",
    "qwen/qwen-2.5-72b-instruct",
]

TASKS = ["popcount32", "xor_cipher16", "mul8", "bitrev16", "binsearch_8x4"]

SYSTEM_PROMPT = """\
You are an expert Verilog RTL designer. Write synthesizable Verilog that complies with Verilator.
Provide your reasoning inside <think>...</think> tags, then provide the final Verilog module inside <answer>...</answer> tags using a ```verilog code block.
No other text outside these tags."""


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


def extract_verilog_for_reporting(response_text: str) -> tuple[str, bool, bool]:
    res = parse_submission(response_text)
    return res.source, res.had_think, res.had_answer


async def call_openrouter(
    client: httpx.AsyncClient, model: str, task_prompt: str, timeout: float = 180.0,
    max_retries: int = 3, verbose: bool = False,
) -> tuple[str, dict]:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": task_prompt}],
        "max_tokens": 2048,
        "temperature": 0.2,
        "stream": True,
    }
    
    for attempt in range(max_retries):
        full_content = []
        try:
            async with client.stream("POST", OPENROUTER_URL, json=payload, timeout=timeout) as resp:
                if resp.status_code == 429:
                    wait = 2 ** attempt * 5
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "): continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]": break
                    try:
                        data = json.loads(data_str)
                        choice = data.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        chunk = delta.get("content") or delta.get("reasoning") or ""
                        if chunk:
                            full_content.append(chunk)
                            if verbose:
                                print(chunk, end="", flush=True)
                    except json.JSONDecodeError: continue
            return "".join(full_content), {}
        except Exception as e:
            if attempt == max_retries - 1: raise
            await asyncio.sleep(2)
    raise RuntimeError(f"API failed after {max_retries} attempts")


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
    task_prompt: str = ""
    raw_response: str = ""
    extracted_verilog: str = ""
    sim_stdout: str = ""
    sim_stderr: str = ""
    timestamp: str = ""
    had_think: bool = False
    had_answer: bool = False


async def run_single(
    client: httpx.AsyncClient, 
    model: str, 
    task_name: str, 
    semaphore: asyncio.Semaphore,
    seed: int = 42, 
    verbose: bool = False
) -> RunResult:
    async with semaphore:
        result = RunResult(
            model=model,
            task=task_name,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        task = TASK_REGISTRY[task_name]
        result.baseline = float(task.baseline_cycles)
        result.task_prompt = task.prompt

        if verbose:
            print(f"\n=== STARTING: {model} / {task_name} ===")

        t0 = time.monotonic()
        try:
            raw_response, usage = await call_openrouter(client, model, task.prompt, verbose=verbose)
        except Exception as e:
            result.error = str(e)
            result.api_latency_s = time.monotonic() - t0
            return result
        result.api_latency_s = time.monotonic() - t0
        result.raw_response = raw_response

        verilog, had_think, had_answer = extract_verilog_for_reporting(raw_response)
        result.had_think = had_think
        result.had_answer = had_answer
        result.extracted_verilog = verilog
        result.extraction_ok = bool(verilog and "module dut" in verilog)

        workdir = Path(tempfile.mkdtemp(prefix="vibe_"))
        env = FPGAEnvironment(
            sandbox=SubprocessSandbox(),
            workdir=workdir,
            n_validation_seeds=2,
            format_bonus=0.05,
        )
        env.reset(seed=seed, task_id=task_name)
        # Use the NEW step_async method we just added to RLVREnvironment!
        obs = await env.step_async(SubmissionAction(source=raw_response))

        result.verdict = obs.verdict.value
        result.score = obs.score
        result.raw_cycles = obs.raw_metric
        result.sim_stdout = obs.stdout
        result.sim_stderr = obs.stderr
        if obs.verdict != Verdict.OK and obs.stderr:
            result.error = obs.stderr[:200]
        
        if verbose:
            print(f"\n--- FINAL ({model} / {task_name}): {result.verdict} score={result.score:.3f}")
        
        return result


VERDICT_EMOJI = {
    "ok": "✅",
    "compile_error": "🔴",
    "incorrect": "❌",
    "timeout": "⏱️",
    "forbidden": "🚫",
    "API_ERROR": "🌐",
}


def write_transcript(r: RunResult, out_dir: Path) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9._-]", "_", r.model)
    fname = out_dir / f"{r.timestamp[:10]}_{slug}_{r.task}.md"
    emoji = VERDICT_EMOJI.get(r.verdict, "❓")
    score_str = f"{r.score:.3f}" if r.score else "0.000"
    cycles_str = f"{r.raw_cycles:.0f}" if r.raw_cycles is not None else "—"
    baseline_str = f"{r.baseline:.0f}" if r.baseline is not None else "—"
    
    lines = [
        f"# {emoji} {r.model} — {r.task}",
        "",
        f"> **Verdict:** `{r.verdict}`  **Score:** `{score_str}`  "
        f"**Cycles:** `{cycles_str}` / `{baseline_str}` baseline  "
        f"**API:** `{r.api_latency_s:.1f}s`  **Tokens:** —\n"
        f"> **Format:** think={r.had_think}, answer={r.had_answer}\n"
        f"> Timestamp: `{r.timestamp}`  Seed: `42`",
        "",
        "---",
        "",
        "## Prompt",
        "",
        "**System:**",
        "```",
        SYSTEM_PROMPT,
        "```",
        "",
        "**User:**",
        "```",
        r.task_prompt.strip(),
        "```",
        "",
        "---",
        "",
        "## Model response",
        "",
        r.raw_response or "*(no response)*",
        "",
        "---",
        "",
        "## Extracted Verilog",
        "",
        "```verilog",
        r.extracted_verilog,
        "```",
        "",
        "---",
        "",
        "## Simulation result",
        "",
        f"**Verdict:** `{r.verdict}`",
        "",
    ]
    if r.sim_stdout:
        lines += ["**Stdout:**", "```", r.sim_stdout.strip(), "```", ""]
    if r.sim_stderr:
        lines += ["**Stderr:**", "```", r.sim_stderr.strip(), "```", ""]
    if r.error and not r.sim_stderr:
        lines += ["**Error:**", "```", r.error, "```", ""]

    fname.write_text("\n".join(lines), encoding="utf-8")
    return fname


def print_table(results: list[RunResult]) -> None:
    hdr = f"{'Model':<42} {'Task':<18} {'Verdict':<16} {'Score':>6} {'Cycles':>8} {'Base':>8} {'API(s)':>7}"
    sep = "-" * len(hdr)
    print(f"\n{sep}\n{hdr}\n{sep}")
    for r in sorted(results, key=lambda x: (x.model, x.task)):
        cyc = f"{r.raw_cycles:.0f}" if r.raw_cycles is not None else "-"
        base = f"{r.baseline:.0f}" if r.baseline is not None else "-"
        print(f"{r.model:<42} {r.task:<18} {r.verdict:<16} {r.score:>6.3f} {cyc:>8} {base:>8} {r.api_latency_s:>7.1f}")
    print(sep)


async def main():
    parser = argparse.ArgumentParser(description="LLM vibe tests for FPGA env (Async)")
    parser.add_argument("--models", type=str, default=None)
    parser.add_argument("--tasks", type=str, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent runs")
    parser.add_argument("--no-transcripts", action="store_true")
    args = parser.parse_args()

    models = args.models.split(",") if args.models else MODELS
    tasks = args.tasks.split(",") if args.tasks else TASKS
    api_key = load_api_key()

    print(f"Models: {models}")
    print(f"Tasks:  {tasks}")
    print(f"Concurrency: {args.concurrency}")
    
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    semaphore = asyncio.Semaphore(args.concurrency)
    
    results: list[RunResult] = []
    
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {api_key}"}) as client:
        # Use TaskGroup if available (Py 3.11+), else gather
        tasks_to_run = []
        for model in models:
            for task_name in tasks:
                tasks_to_run.append(run_single(
                    client, model, task_name, semaphore, 
                    seed=args.seed, verbose=(len(models)*len(tasks) == 1)
                ))
        
        results = await asyncio.gather(*tasks_to_run)

    for r in results:
        if not args.no_transcripts:
            write_transcript(r, TRANSCRIPTS_DIR)

    print_table(results)
    
    ok = sum(1 for r in results if r.verdict == "ok")
    print(f"\nSummary: {ok}/{len(results)} OK. See transcripts/ for details.")


if __name__ == "__main__":
    asyncio.run(main())

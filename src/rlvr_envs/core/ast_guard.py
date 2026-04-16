"""Lightweight Python AST denylist for reward-hack prevention.

Primary threats we care about (ordered by expected frequency in training):

    1. Importing a high-level library that trivialises the task
       (`numpy.linalg.solve` for matrix inversion, `cryptography.Fernet` for
       encryption, `zlib` for "implement a compressor", etc).
    2. Shelling out to the system (`os.system`, `subprocess`, `os.popen`)
       to invoke the reference implementation directly.
    3. Reading files the task wanted the model to produce from memory.

This is a static check: we do not try to outsmart `exec`/`eval`. Environments
that care about that either (a) ban exec/eval outright via this guard, or (b)
run submissions in a locked-down subprocess with unlinked FDs, or both.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class GuardReport:
    ok: bool
    violations: List[str] = field(default_factory=list)


class PythonASTGuard:
    """Static denylist. `denied_modules` matches on full dotted prefix:
    `denied_modules=('numpy',)` blocks `numpy`, `numpy.linalg`, `numpy.linalg.solve`."""

    def __init__(
        self,
        denied_modules: Sequence[str] = (),
        denied_names: Sequence[str] = (),
        allow_exec: bool = False,
    ) -> None:
        self._denied_modules = tuple(denied_modules)
        self._denied_names = frozenset(denied_names)
        self._allow_exec = allow_exec

    def check(self, source: str) -> GuardReport:
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return GuardReport(ok=False, violations=[f"SyntaxError: {e.msg}"])

        violations: List[str] = []
        for node in ast.walk(tree):
            violations.extend(self._check_node(node))

        return GuardReport(ok=not violations, violations=violations)

    def _check_node(self, node: ast.AST) -> Iterable[str]:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bad = self._match_module(alias.name)
                if bad is not None:
                    yield f"import of denied module: {alias.name} (matched {bad})"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            bad = self._match_module(mod)
            if bad is not None:
                yield f"from-import of denied module: {mod} (matched {bad})"
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name is not None and name in self._denied_names:
                yield f"call to denied name: {name}"
            if not self._allow_exec and name in ("exec", "eval", "compile"):
                yield f"call to {name}() is not allowed in this environment"
        elif isinstance(node, ast.Attribute):
            # e.g. os.system, subprocess.run reached via attribute chain
            flat = _flatten_attr(node)
            if flat and flat in self._denied_names:
                yield f"use of denied attribute: {flat}"

    def _match_module(self, name: str) -> Optional[str]:
        for prefix in self._denied_modules:
            if name == prefix or name.startswith(prefix + "."):
                return prefix
        return None


def _call_name(func: ast.AST) -> Optional[str]:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return _flatten_attr(func)
    return None


def _flatten_attr(node: ast.AST) -> Optional[str]:
    parts: List[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    else:
        return None
    return ".".join(reversed(parts))

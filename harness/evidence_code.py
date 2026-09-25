"""Code-path evidence sets, derived from each operator's IMPLEMENTATION (STAGE4 Part 1 prep; DECISIONS
2026-09-25).

The blind audit (FINDINGS F16) found a valid evidence path the operators' evidence sets did not admit:
the fault's config key → the workload code that consumes it → the mechanism function. Every operator
now declares, in its own module, WHERE its fault is implemented in the workload source (``CODE_PATH``):

  ("train.py", "reads", "<key>")        the FIRST statement that reads the knob (a string literal used
                                         as a ``.get(...)`` key or a subscript), plus — when that
                                         statement is an assignment whose target the NEXT statement's
                                         test uses — the block it gates;
  ("datautil.py", "function", "<name>") the mechanism function's full ``def`` span.

The spans are RESOLVED (``ast``) against the case's own workspace source at score time, so they are
correct for whichever train.py a case shipped — never hard-coded line numbers, never derived from
observed agent citations. Refs use kind ``code_span`` (the submit schema's kind for code; agents cite
code as code_span ~23× more often than as line_range in H8).
"""
from __future__ import annotations

import ast
from pathlib import Path


def _stmt_bodies(tree: ast.AST):
    """Every statement list (module / function / class / if / loop bodies), in source order."""
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody", "handlers"):
            seq = getattr(node, field, None)
            if isinstance(seq, list) and seq and all(isinstance(s, ast.stmt) for s in seq):
                yield seq


def _reads_key(node: ast.AST, key: str) -> bool:
    """True if ``node`` reads ``key``: ``x.get("key", ...)`` or ``x["key"]`` (load context)."""
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "get"
                and sub.args and isinstance(sub.args[0], ast.Constant) and sub.args[0].value == key):
            return True
        if (isinstance(sub, ast.Subscript) and isinstance(sub.ctx, ast.Load)
                and isinstance(sub.slice, ast.Constant) and sub.slice.value == key):
            return True
    return False


def first_read_span(source: str, key: str) -> tuple[int, int] | None:
    """(start, end) lines of the innermost statement that FIRST reads ``key`` (+ the block it gates)."""
    tree = ast.parse(source)
    best = None                                   # (lineno, depth, stmt, siblings, index)
    for body in _stmt_bodies(tree):
        for i, stmt in enumerate(body):
            if _reads_key(stmt, key):
                inner = [s for s in ast.walk(stmt) if isinstance(s, ast.stmt) and s is not stmt
                         and _reads_key(s, key)]
                if inner:
                    continue                      # a nested statement is more specific
                cand = (stmt.lineno, stmt, body, i)
                if best is None or cand[0] < best[0]:
                    best = cand
    if best is None:
        return None
    _, stmt, body, i = best
    start, end = stmt.lineno, stmt.end_lineno
    if isinstance(stmt, ast.Assign) and i + 1 < len(body) and isinstance(body[i + 1], ast.If):
        targets = {t.id for t in stmt.targets if isinstance(t, ast.Name)}
        used = {n.id for n in ast.walk(body[i + 1].test) if isinstance(n, ast.Name)}
        if targets & used:
            end = body[i + 1].end_lineno          # the read + the block it gates
    return start, end


def function_span(source: str, name: str) -> tuple[int, int] | None:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node.lineno, node.end_lineno
    return None


def code_path_refs(code_path, workspace: Path) -> list[dict] | None:
    """Resolve an operator's CODE_PATH against a workspace → code_span refs (None if any anchor fails
    to resolve — an unresolvable set is never silently shrunk)."""
    refs = []
    for artifact, how, name in code_path:
        path = Path(workspace) / artifact
        if not path.is_file():
            return None
        src = path.read_text()
        try:
            span = first_read_span(src, name) if how == "reads" else function_span(src, name)
        except SyntaxError:
            return None                           # unparseable source → no set, never a guess
        if span is None:
            return None
        refs.append({"kind": "code_span", "artifact_id": artifact,
                     "detail": {"start_line": span[0], "end_line": span[1]}})
    return refs

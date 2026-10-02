"""Validate a submission directory with the organizers' own compiler before spending GPU time.

Checks: single declared model, allowed extensions + size, compile_submission() with stub tools,
skill dirs present, and lists the compiled agent tree.
Usage: .venv-eval/bin/python -m src.eval.validate_submission submissions/c1
"""

from __future__ import annotations

import sys
from pathlib import Path

from adk_submission import compile_submission
from swegemma.config import ALLOWED_SUBMISSION_EXTENSIONS, MAX_SUBMISSION_SIZE_BYTES, build_submission_limits
from swegemma.models.discovery import validate_single_declared_model
from swegemma.models.registry import setup_gemma_model_registry


def run_command(command: str) -> str:
    """Execute a shell command in /workspace."""
    return ""


def submit_patch() -> str:
    """Submit the current diff."""
    return ""


def get_status() -> str:
    """Budget status."""
    return ""


def read_file(filepath: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read a file."""
    return ""


def edit_file(filepath: str, old_string: str, new_string: str, allow_multiple: bool = False) -> str:
    """Edit a file."""
    return ""


def write_file(filepath: str, content: str) -> str:
    """Write a file."""
    return ""


def get_code_neighbors(node: str, edge_type: str | None = None, max_neighbors: int = 50) -> str:
    """Graph neighbors."""
    return ""


def search_similar_code(query: str, k: int = 10) -> str:
    """Embedding search."""
    return ""


def get_code_subgraph(nodes: list[str]) -> str:
    """Induced subgraph."""
    return ""


TOOLS = {f.__name__: f for f in (run_command, submit_patch, get_status, read_file, edit_file, write_file,
                                  get_code_neighbors, search_similar_code, get_code_subgraph)}


def describe(agent, depth: int = 0) -> None:
    tools = [getattr(t, "name", type(t).__name__) for t in getattr(agent, "tools", []) or []]
    print("  " * depth + f"- {agent.name} ({type(agent).__name__}) model={getattr(agent, 'model', None)!s:.60} tools={tools}")
    for sa in getattr(agent, "sub_agents", []) or []:
        describe(sa, depth + 1)


def main(sub_dir: str) -> int:
    sub = Path(sub_dir).resolve()
    ok = True
    total = 0
    for p in sub.rglob("*"):
        if p.is_symlink():
            print("FAIL symlink:", p)
            ok = False
        if p.is_file():
            total += p.stat().st_size
            if p.suffix.lower() not in ALLOWED_SUBMISSION_EXTENSIONS:
                print("FAIL disallowed extension:", p.relative_to(sub))
                ok = False
    print(f"size {total / 2**20:.2f} MiB (limit {MAX_SUBMISSION_SIZE_BYTES / 2**30:.0f} GiB)")
    ok &= total < MAX_SUBMISSION_SIZE_BYTES
    model = validate_single_declared_model(sub)
    print("declared model:", model)
    limits, gen = build_submission_limits()
    agent = compile_submission(
        submission_dir=sub, tool_registry=TOOLS, model_registry=setup_gemma_model_registry(),
        code_executor=None, script_timeout=120, limits=limits, generation_constraints=gen,
    )
    describe(agent)
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

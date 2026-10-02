"""Shared helpers for repo-tools scripts (stdlib only; runs inside the evaluation sandbox)."""

import ast
import os
import re

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "build", "dist", ".tox", ".venv", "venv", "node_modules", "site"}
TEST_DIRS = {"tests", "test", "testing"}

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
STOP = set(
    """a an the and or but if then else of to in on for with without by from as at is are was were be been being
    this that these those it its we you i he she they them our your their not no yes do does did done can could
    should would will may might must have has had there here when where which who what why how all any some
    such than too very just also only into out up down over under again further once more most other same so
    pr fix fixes fixed issue issues add added adds adding update updated use used uses using support new now
    see https http github com www self cls none true false return def class import""".split()
)


def repo_root() -> str:
    """The repository the agent works on (skill scripts run from a temp dir)."""
    for cand in (os.environ.get("SWE_WORKSPACE"), os.environ.get("PWD"), "/workspace"):
        if cand and os.path.isdir(os.path.join(cand, ".git")):
            return cand
    d = os.getcwd()
    while d != "/":
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return "/workspace"


def iter_py_files(root: str, include_tests: bool = False):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        is_test_dir = any(p in TEST_DIRS for p in parts)
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            is_test = is_test_dir or fn.startswith("test_") or fn.endswith("_test.py") or fn == "conftest.py"
            if is_test and not include_tests:
                continue
            yield os.path.join(rel_dir, fn) if parts else fn


def split_ident(tok: str):
    out = []
    for p in tok.split("_"):
        if p:
            out.extend(x.lower() for x in _CAMEL.split(p) if x)
    return out


def tokenize(text: str):
    out = []
    for w in _WORD.findall(text):
        subs = split_ident(w)
        if len(subs) > 1:
            out.append(w.lower())
        out.extend(subs)
    return [t for t in out if len(t) > 1 and t not in STOP and not t.isdigit()]


def definitions(src: str):
    """Yield (qualname, kind, start_line, end_line, node) for every def/class (decorators included)."""
    tree = ast.parse(src)
    stack = [(tree, "")]
    while stack:
        node, prefix = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{prefix}.{child.name}" if prefix else child.name
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                kind = "class" if isinstance(child, ast.ClassDef) else "def"
                yield q, kind, start, child.end_lineno, child
                stack.append((child, q))
            elif not isinstance(child, ast.Lambda):
                stack.append((child, prefix))


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def clip(text: str, limit: int = 4500) -> str:
    return text if len(text) <= limit else text[: limit - 40] + "\n... [truncated]"

"""patch-check: one deterministic pre-submit check of the working tree in /workspace.

Usage (via run_skill_script, args dict -> --key value):
    check.py [--tests "<pytest args>"] [--repro /tmp/repro.py] [--budget 170]

Steps (compact report, <= 40 lines):
  1. files changed vs the _swegemma_baseline tag (EMPTY if none)
  2. removes scratch files (repro*/debug*/scratch*/test_*.py at root, *.orig/*.rej/*.bak, stray caches) and
     reverts edited/added test, conftest, pytest/tox/packaging-config and CI files
  3. syntax check (compile) + import check of every changed .py module
  4. repro A/B: /tmp/repro.py on the ORIGINAL code (git worktree at /tmp/_base) and on the patched code
  5. optional: python -m pytest -x -q <tests>
  6. sibling implementations / call sites of every changed function
  7. VERDICT: OK | FAIL (<reasons>)
Stdlib only; Python 3.6+. Never edits source files; only removes scratch files and reverts protected files.
"""
import ast
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

TAG = "_swegemma_baseline"
BASE_DIR = os.environ.get("PATCHCHECK_BASE_DIR") or None  # resolved after _tmp is defined
MAX_LINES = 40
T0 = time.time()
DEADLINE = [T0 + 170.0]

PROTECTED_NAMES = {
    "conftest.py", "pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg", ".pytest.ini",
    "sitecustomize.py", "usercustomize.py", "_swegemma_stubs.py", "MANIFEST.in",
    ".travis.yml", ".gitlab-ci.yml", "azure-pipelines.yml", "appveyor.yml", ".coveragerc", "noxfile.py",
}
CI_DIRS = (".github/", ".circleci/", ".azure-pipelines/", ".ci/")
SCRATCH_ROOT_RE = re.compile(r"^(repro|reproduce|debug|scratch|tmp_|temp_)[^/]*$|^test_[^/]*\.py$", re.I)
SCRATCH_ANY_RE = re.compile(r"\.(orig|rej|bak|swp|pyc)$|(^|/)(__pycache__|\.pytest_cache)/")
IGNORE_RE = re.compile(r"(^|/)\.adk_exec_[0-9a-f]+\.py$")  # harness skill-runner temp file; it removes it itself
SKIP_DIRS = ("build", "dist", ".tox", ".nox", ".venv", "venv", "env", "node_modules", ".eggs", "site-packages", ".git")


def find_root():
    # Kaggle scorer (docker): /workspace. Local subprocess sandbox: the skill runner chdirs to a temp dir, but bash's
    # $PWD and $PYTHONPATH still point at the repo. Prefer a candidate that is a git checkout.
    cands = [os.environ.get("SWE_WORKSPACE"), "/workspace", os.environ.get("PWD")]
    cands += os.environ.get("PYTHONPATH", "").split(os.pathsep) + [os.getcwd()]
    cands = [c for c in cands if c and os.path.isdir(c)]
    for c in cands:
        if os.path.isdir(os.path.join(c, ".git")):
            return os.path.abspath(c)
    return os.path.abspath(cands[0]) if cands else "."


def _tmp(path):
    # "/tmp/x" as the agent's shell sees it: real /tmp in the scorer container, $TMPDIR in the local sandbox.
    if os.path.isdir("/workspace") or not path.startswith("/tmp"):
        return path
    return os.path.join(os.environ.get("TMPDIR") or "/tmp", path[len("/tmp"):].lstrip("/"))


ROOT = find_root()
BASE_DIR = BASE_DIR or _tmp("/tmp/_base")


def remaining():
    return DEADLINE[0] - time.time()


def run(cmd, cwd=None, timeout=60, env=None, inp=None):
    """Run cmd (list or shell str); return (rc, output). rc None = timeout, rc -999 = could not start."""
    timeout = max(1.0, min(float(timeout), remaining()))
    try:
        p = subprocess.Popen(cmd, cwd=cwd or ROOT, env=env, shell=isinstance(cmd, str),
                             stdin=subprocess.PIPE if inp is not None else subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True, errors="replace", start_new_session=True)
    except (OSError, ValueError) as e:
        return -999, str(e)
    try:
        out, _ = p.communicate(inp, timeout=timeout)
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
        try:
            out, _ = p.communicate(timeout=5)
        except Exception:
            out = ""
        return None, out or ""


def git(args, timeout=30, cwd=None):
    return run(["git", "-c", "core.quotepath=off"] + args, cwd=cwd, timeout=timeout)


def py_exe():
    """The interpreter the agent uses (`python` on PATH), not necessarily the one running this script."""
    for name in ("python", "python3"):
        p = shutil.which(name)
        if p:
            return p
    return sys.executable


def py_env(base_paths):
    env = dict(os.environ)
    keep = [p for p in env.get("PYTHONPATH", "").split(os.pathsep)
            if p and not p.startswith(ROOT) and not p.startswith(BASE_DIR)]
    env["PYTHONPATH"] = os.pathsep.join(base_paths + keep)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def src_paths(root):
    return [root] + ([os.path.join(root, "src")] if os.path.isdir(os.path.join(root, "src")) else [])


def last_line(out, n=160):
    lines = [l.strip() for l in (out or "").strip().splitlines() if l.strip()]
    if not lines:
        return ""
    s = lines[-1]
    return s if len(s) <= n else s[:n] + "..."


def is_protected(path):
    name = path.rsplit("/", 1)[-1]
    if name in PROTECTED_NAMES or name.endswith(".pth") or path.startswith(CI_DIRS):
        return True
    if re.match(r"requirements[^/]*\.txt$", name):
        return True
    if name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")):
        return True
    parts = set(p.lower() for p in path.split("/")[:-1])
    return bool(parts & {"tests", "test", "testing"}) and name.endswith(".py")


def changed_files(base):
    """[(status, path)] working tree vs base, incl. untracked (status '?')."""
    res = []
    rc, out = git(["diff", "--name-status", "-z", "--no-renames", base])
    if rc == 0:
        toks = out.split("\0")
        i = 0
        while i + 1 < len(toks):
            st, p = toks[i].strip(), toks[i + 1]
            i += 2
            if st and p:
                res.append((st[0], p))
    rc, out = git(["ls-files", "-z", "--others", "--exclude-standard"])
    if rc == 0:
        seen = set(p for _, p in res)
        for p in out.split("\0"):
            if p and p not in seen:
                res.append(("?", p))
    return [(s, p) for s, p in res if not IGNORE_RE.search(p)]


def tracked_in_base(base, path):
    rc, _ = git(["cat-file", "-e", "%s:%s" % (base, path)], timeout=10)
    return rc == 0


def cleanup(base, files, log):
    """Remove scratch files, revert protected files. Returns remaining changed files."""
    keep = []
    for st, p in files:
        new = st in ("?", "A")
        full = os.path.join(ROOT, p)
        scratch = new and ((("/" not in p) and SCRATCH_ROOT_RE.match(p)) or SCRATCH_ANY_RE.search(p))
        if scratch:
            try:
                os.remove(full)
                git(["rm", "-q", "--cached", "--ignore-unmatch", "--", p], timeout=10)
                log.append("removed scratch file %s" % p)
            except OSError as e:
                log.append("could not remove %s: %s" % (p, e))
                keep.append((st, p))
            continue
        if is_protected(p):
            if new and not tracked_in_base(base, p):
                try:
                    os.remove(full)
                    git(["rm", "-q", "--cached", "--ignore-unmatch", "--", p], timeout=10)
                    log.append("removed new protected file %s (tests/config are not part of a fix)" % p)
                except OSError as e:
                    log.append("could not remove %s: %s" % (p, e))
                    keep.append((st, p))
            else:
                rc, out = git(["checkout", base, "--", p], timeout=20)
                if rc == 0:
                    log.append("reverted %s to baseline (test/config/CI file; the grader discards such edits)" % p)
                else:
                    log.append("could not revert %s: %s" % (p, last_line(out)))
                    keep.append((st, p))
            continue
        keep.append((st, p))
    return keep


def module_name(path):
    """Dotted module for a repo-relative .py path, or None if not importable as a package module."""
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
        d = os.path.dirname(os.path.join(ROOT, path))
    else:
        d = os.path.dirname(os.path.join(ROOT, path))
    rel_dir = os.path.relpath(d, ROOT)
    dir_parts = [] if rel_dir == "." else rel_dir.split(os.sep)
    # walk up while the directory is a package
    n_pkg = 0
    cur = d
    while n_pkg < len(dir_parts) and os.path.isfile(os.path.join(cur, "__init__.py")):
        n_pkg += 1
        cur = os.path.dirname(cur)
    top = dir_parts[:len(dir_parts) - n_pkg]  # directories that are not packages
    if top not in ([], ["src"]):
        return None
    mod_parts = dir_parts[len(top):] + ([] if path.endswith("__init__.py") else [parts[-1]])
    if not mod_parts or not all(re.match(r"^[A-Za-z_]\w*$", x) for x in mod_parts):
        return None
    if len(mod_parts) == 1 and mod_parts[0] in ("setup", "conftest", "manage", "noxfile", "fabfile"):
        return None  # importing these runs them
    return ".".join(mod_parts)


IMPORT_SNIPPET = r"""
import importlib, sys, traceback
for m in sys.argv[1:]:
    try:
        importlib.import_module(m)
        print("IMPORT_OK " + m)
    except BaseException as e:
        msg = (type(e).__name__ + ": " + str(e)).replace("\n", " ")[:200]
        print("IMPORT_FAIL " + m + " :: " + msg)
    sys.stdout.flush()
"""

COMPILE_SNIPPET = r"""
import sys
for f in sys.argv[1:]:
    try:
        with open(f, "rb") as fh:
            compile(fh.read(), f, "exec")
        print("SYN_OK " + f)
    except SyntaxError as e:
        print("SYN_FAIL %s:%s: %s" % (f, e.lineno, e.msg))
    except Exception as e:
        print("SYN_FAIL %s: %s" % (f, e))
"""


def check_imports(mods, root, timeout):
    rc, out = run([py_exe(), "-c", IMPORT_SNIPPET] + mods, cwd=root, timeout=timeout, env=py_env(src_paths(root)))
    res = {}
    for line in out.splitlines():
        if line.startswith("IMPORT_OK "):
            res[line[10:].strip()] = None
        elif line.startswith("IMPORT_FAIL "):
            m, _, msg = line[12:].partition(" :: ")
            res[m.strip()] = msg.strip()
    for m in mods:
        if m not in res:
            res[m] = "import timed out" if rc is None else ("no result: " + last_line(out))
    return res


def ensure_base_worktree(base):
    """Create (or reuse) a pristine checkout of the baseline at /tmp/_base. Returns error string or None."""
    rc, head = git(["rev-parse", base + "^{commit}"], timeout=10)
    want = head.strip()
    if os.path.isdir(BASE_DIR):
        rc2, cur = git(["rev-parse", "HEAD"], timeout=10, cwd=BASE_DIR)
        if rc2 == 0 and cur.strip() == want and os.path.exists(os.path.join(BASE_DIR, ".git")):
            git(["reset", "-q", "--hard", want], timeout=60, cwd=BASE_DIR)
            git(["clean", "-fdq"], timeout=30, cwd=BASE_DIR)
            return None
        git(["worktree", "remove", "--force", BASE_DIR], timeout=30)
        shutil.rmtree(BASE_DIR, ignore_errors=True)
        git(["worktree", "prune"], timeout=10)
    rc, out = git(["worktree", "add", "-f", "--detach", BASE_DIR, want], timeout=90)
    if rc != 0:  # very old git: fall back to an exported tree
        shutil.rmtree(BASE_DIR, ignore_errors=True)
        os.makedirs(BASE_DIR)
        rc, out = run("git archive %s | tar -x -C %s" % (shlex.quote(want), BASE_DIR), timeout=90)
        if rc != 0:
            return "could not create baseline checkout: " + last_line(out)
    copy_build_artifacts()
    return None


def copy_build_artifacts():
    """Copy git-ignored compiled extensions / generated version files so the baseline is importable."""
    rc, out = git(["ls-files", "-z", "--others", "--ignored", "--exclude-standard"], timeout=20)
    if rc != 0:
        return
    n = 0
    for p in out.split("\0"):
        if not p or n >= 300:
            continue
        segs = p.split("/")
        if any(s in SKIP_DIRS for s in segs[:-1]):
            continue
        name = segs[-1]
        if not (name.endswith((".so", ".pyd")) or re.match(r"^_?version\.py$", name)):
            continue
        dst = os.path.join(BASE_DIR, p)
        if os.path.exists(dst):
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, p), dst)
            n += 1
        except (OSError, IOError):
            pass


def remove_base_worktree():
    git(["worktree", "remove", "--force", BASE_DIR], timeout=30)
    shutil.rmtree(BASE_DIR, ignore_errors=True)
    git(["worktree", "prune"], timeout=10)


def run_repro(path, cwd, timeout):
    rc, out = run([py_exe(), path], cwd=cwd, timeout=timeout, env=py_env(src_paths(cwd)))
    if rc is None:
        return "TIMEOUT", "FAIL(timeout)", out
    if rc == -999:
        return "ERROR", "FAIL(not run)", out
    return ("PASS" if rc == 0 else "FAIL"), "%s(%d)" % ("PASS" if rc == 0 else "FAIL", rc), out


def changed_lines(base, path):
    rc, out = git(["diff", "-U0", base, "--", path], timeout=20)
    lines = set()
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", out, re.M):
        start, cnt = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        if cnt == 0:
            lines.update([start, start + 1])
        else:
            lines.update(range(start, start + cnt))
    return lines


def enclosing_functions(path, lines):
    """{(qualname, def_line)} of innermost defs containing the changed lines."""
    try:
        with open(os.path.join(ROOT, path), "rb") as fh:
            src = fh.read()
        tree = ast.parse(src)
    except Exception:
        return regex_functions(path, lines)
    spans = []

    def visit(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                end = max(getattr(n, "lineno", ch.lineno) for n in ast.walk(ch))
                start = min([ch.lineno] + [d.lineno for d in getattr(ch, "decorator_list", [])])
                q = prefix + ch.name
                if not isinstance(ch, ast.ClassDef):
                    spans.append((start, end, q, ch.name, ch.lineno))
                visit(ch, q + ".")
            else:
                visit(ch, prefix)
    visit(tree, "")
    found = {}
    for ln in sorted(lines):
        best = None
        for s, e, q, name, dl in spans:
            if s <= ln <= e and (best is None or s >= best[0]):
                best = (s, e, q, name, dl)
        if best:
            found[best[2]] = (best[3], best[4])
    return found


def regex_functions(path, lines):
    found = {}
    try:
        with open(os.path.join(ROOT, path), errors="replace") as fh:
            src = fh.read().splitlines()
    except Exception:
        return found
    for ln in sorted(lines):
        for i in range(min(ln, len(src)) - 1, -1, -1):
            m = re.match(r"\s*(?:async\s+)?def\s+(\w+)", src[i])
            if m:
                found[m.group(1)] = (m.group(1), i + 1)
                break
    return found


def grep(pattern):
    cmd = ["grep", "-rnE", "--include=*.py"] + ["--exclude-dir=%s" % d for d in SKIP_DIRS] + [pattern, "."]
    rc, out = run(cmd, timeout=20)
    hits = []
    for line in out.splitlines():
        m = re.match(r"^\./(.+?):(\d+):(.*)$", line)
        if m:
            hits.append((m.group(1), int(m.group(2)), m.group(3)))
    return hits


def sibling_hints(base, py_changed, max_funcs=3):
    out = []
    funcs = []
    for p in py_changed:
        for q, (name, dl) in sorted(enclosing_functions(p, changed_lines(base, p)).items(), key=lambda x: x[1][1]):
            funcs.append((p, q, name, dl))
    if not funcs:
        return out
    for p, q, name, dl in funcs[:max_funcs]:
        out.append("  %s:%d %s()" % (p, dl, q))
        if name.startswith("__") and name.endswith("__"):
            continue
        defs = [(f, l) for f, l, _ in grep(r"^\s*(async\s+)?def\s+%s\s*\(" % re.escape(name))
                if not (f == p and l == dl) and not is_protected(f)]
        if defs:
            more = " (+%d more)" % (len(defs) - 5) if len(defs) > 5 else ""
            out.append("    same-name defs: " + ", ".join("%s:%d" % d for d in defs[:5]) + more)
        calls = [(f, l) for f, l, t in grep(r"(^|[^A-Za-z0-9_])%s\s*\(" % re.escape(name))
                 if not is_protected(f) and not re.match(r"\s*(async\s+)?def\s", t)]
        if calls:
            more = " (+%d more)" % (len(calls) - 5) if len(calls) > 5 else ""
            out.append("    call sites: " + ", ".join("%s:%d" % c for c in calls[:5]) + more)
    if len(funcs) > max_funcs:
        out.append("  (+%d more changed functions)" % (len(funcs) - max_funcs))
    return out


def parse_args(argv):
    opts = {"tests": "", "repro": "/tmp/repro.py", "budget": "170"}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--") and a[2:].split("=", 1)[0] in opts:
            if "=" in a:
                k, v = a[2:].split("=", 1)
                opts[k] = v
                i += 1
            else:
                opts[a[2:]] = argv[i + 1] if i + 1 < len(argv) else ""
                i += 2
        else:
            i += 1
    if opts["tests"].strip().lower() in ("none", "null", "false", "''", '""'):
        opts["tests"] = ""
    return opts


def main(argv=None):
    opts = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        DEADLINE[0] = T0 + float(opts["budget"])
    except ValueError:
        pass
    head = []      # always shown
    tail = []      # tests output
    reasons = []
    warns = []

    rc, _ = git(["rev-parse", "-q", "--verify", TAG + "^{commit}"], timeout=10)
    base = TAG if rc == 0 else "HEAD"
    if base != TAG:
        head.append("NOTE: tag %s not found; comparing against HEAD" % TAG)

    # 1+2: changed files, cleanup
    log = []
    files = cleanup(base, changed_files(base), log)
    for l in log[:8]:
        head.append("CLEANUP: " + l)
    if len(log) > 8:
        head.append("CLEANUP: (+%d more)" % (len(log) - 8))
    if not files:
        head.append("CHANGED: EMPTY - no source change vs baseline; the patch would score 0")
        reasons.append("empty patch")
    else:
        desc = ", ".join("%s[%s]" % (p, "new" if s in "?A" else ("del" if s == "D" else "mod")) for s, p in files[:10])
        head.append("CHANGED (%d): %s%s" % (len(files), desc, " ..." if len(files) > 10 else ""))
        for s, p in files:
            if p.rsplit("/", 1)[-1] == "setup.py":
                warns.append("setup.py changed: make sure the fix really needs it")

    py_changed = [p for s, p in files if p.endswith(".py") and s != "D" and os.path.isfile(os.path.join(ROOT, p))]

    # 3: syntax + import
    syntax_bad = set()
    if py_changed:
        rc, out = run([py_exe(), "-c", COMPILE_SNIPPET] + py_changed, timeout=30, env=py_env(src_paths(ROOT)))
        bad = [l[9:] for l in out.splitlines() if l.startswith("SYN_FAIL ")]
        if rc == -999 or (not bad and "SYN_OK" not in out):  # interpreter problem: compile in-process
            bad = []
            for p in py_changed:
                try:
                    with open(os.path.join(ROOT, p), "rb") as fh:
                        compile(fh.read(), p, "exec")
                except SyntaxError as e:
                    bad.append("%s:%s: %s" % (p, e.lineno, e.msg))
        for b in bad:
            head.append("SYNTAX ERROR: " + b)
            syntax_bad.add(b.split(":", 1)[0])
        if bad:
            reasons.append("syntax error")
        else:
            head.append("SYNTAX: OK (%d file%s)" % (len(py_changed), "" if len(py_changed) == 1 else "s"))

    mods, skipped = [], []
    for p in py_changed:
        if p in syntax_bad or is_protected(p):
            continue
        m = module_name(p)
        if m:
            if m not in mods:
                mods.append(m)
        else:
            skipped.append(p)
    base_ready = None  # None = not attempted, "" = ok, str = error
    if mods:
        res = check_imports(mods[:8], ROOT, 60)
        failed = dict((m, e) for m, e in res.items() if e)
        if failed:  # pre-existing failures (missing optional deps etc.) are not the patch's fault
            base_ready = ensure_base_worktree(base) or ""
            if base_ready == "":
                bres = check_imports(sorted(failed), BASE_DIR, 45)
                for m in list(failed):
                    if bres.get(m):
                        warns.append("import %s also fails on ORIGINAL code (ignored): %s" % (m, failed.pop(m)[:100]))
        ok = [m for m in mods[:8] if not res.get(m)]
        if ok:
            head.append("IMPORT: OK " + ", ".join(ok)[:200])
        for m, e in failed.items():
            head.append("IMPORT ERROR: %s :: %s" % (m, e))
        if failed:
            reasons.append("import error")
    if skipped:
        head.append("IMPORT: skipped (not inside an importable package): " + ", ".join(skipped[:4]))

    # 4: repro A/B
    repro = _tmp(opts["repro"])
    if os.path.isfile(repro):
        if remaining() < 15:
            head.append("REPRO: skipped (time budget)")
        else:
            if base_ready is None:
                base_ready = ensure_base_worktree(base) or ""
            if base_ready:
                o_stat, o_txt, o_out = "ERROR", "NOT RUN (%s)" % base_ready, ""
            else:
                try:
                    with open(repro, errors="replace") as fh:
                        txt = fh.read()
                    base_repro = _tmp("/tmp/_repro_base.py")
                    with open(base_repro, "w") as fh:
                        fh.write(txt.replace(ROOT, BASE_DIR))
                    o_stat, o_txt, o_out = run_repro(base_repro, BASE_DIR, min(60, max(5, remaining() / 2 - 5)))
                except (OSError, IOError) as e:
                    o_stat, o_txt, o_out = "ERROR", "NOT RUN (%s)" % e, ""
            p_stat, p_txt, p_out = run_repro(repro, ROOT, 60)
            head.append("REPRO: original=%s patched=%s" % (o_txt, p_txt))
            if o_stat == "PASS":
                head.append("  -> original PASSES: repro does not reproduce the bug: it is not evidence")
                if p_stat == "PASS" and o_out.strip() != p_out.strip():
                    head.append("  outputs differ: original '%s' vs patched '%s'" % (last_line(o_out, 70), last_line(p_out, 70)))
            elif o_stat in ("FAIL", "TIMEOUT") and o_out:
                head.append("  original: " + last_line(o_out))
            if p_stat in ("FAIL", "TIMEOUT"):
                head.append("  patched: " + last_line(p_out))
                head.append("  -> fix does not work (repro still fails on the patched code)")
                reasons.append("repro fails on patched code")
            elif p_stat == "PASS" and o_stat in ("FAIL", "TIMEOUT"):
                head.append("  -> good: fails on original, passes with the patch")
    else:
        head.append("REPRO: none (%s not found)" % repro)
    if base_ready == "" or os.path.isdir(BASE_DIR):
        remove_base_worktree()

    # 5: tests
    if opts["tests"].strip():
        if remaining() < 15:
            tail.append("TESTS: skipped (time budget)")
        else:
            try:
                targs = shlex.split(opts["tests"])
            except ValueError:
                targs = opts["tests"].split()
            if targs[:3] == ["python", "-m", "pytest"]:
                targs = targs[3:]
            elif targs[:1] in (["pytest"], ["py.test"]):
                targs = targs[1:]
            cmd = [py_exe(), "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"] + targs
            rc, out = run(cmd, timeout=120, env=py_env(src_paths(ROOT)))
            status = "TIMEOUT" if rc is None else ("PASS" if rc == 0 else ("NO TESTS COLLECTED" if rc == 5 else "FAIL(%d)" % rc))
            tail.append("TESTS: %s  [pytest -x -q %s]" % (status, " ".join(targs)[:120]))
            tail.extend("  " + l[:200] for l in [x for x in out.splitlines() if x.strip()][-15:])
            if status.startswith("FAIL") or status == "TIMEOUT":
                warns.append("tests fail: check whether they also fail without your change")
        # tests may leave artifacts behind
        log2 = []
        cleanup(base, [f for f in changed_files(base) if f[0] in "?A"], log2)
        for l in log2[:3]:
            tail.append("CLEANUP: " + l)

    # 6: sibling / caller hints
    hint_room = MAX_LINES - len(head) - len(tail) - len(warns) - 2
    hints = []
    if py_changed and hint_room >= 2 and remaining() > 5:
        srcs = [p for p in py_changed if not is_protected(p) and p not in syntax_bad
                and any(s not in "?A" for s, q in files if q == p)]
        hints = sibling_hints(base, srcs)
        if hints:
            hints = ["SIBLINGS/CALLERS (does the same bug exist there too?):"] + hints
            hints = hints[:hint_room]

    lines = head + tail + hints + ["WARN: " + w for w in warns[:4]]
    lines = lines[:MAX_LINES - 1]
    lines.append("VERDICT: OK" if not reasons else "VERDICT: FAIL (%s)" % "; ".join(reasons))
    print("\n".join(lines))
    sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never crash the agent's tool call
        print("patch-check internal error: %s: %s" % (type(e).__name__, e))
        print("VERDICT: OK (check incomplete)")

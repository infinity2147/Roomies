"""apply-edit: apply SEARCH/REPLACE blocks to files in /workspace from ONE string argument; syntax-checked.

Why: Gemma's multi-argument edit_file calls are malformed ~84% of the time on our proxy (a stray backtick ends
new_string and swallows old_string). A single string argument cannot lose a sibling argument.

Block format (one or more blocks; the path line precedes each block):
    path/to/file.py
    <<<<<<< SEARCH
    exact lines currently in the file
    =======
    replacement lines
    >>>>>>> REPLACE
An empty SEARCH section creates a new file (or appends to an empty one).
Matching: exact -> ignoring trailing whitespace -> ignoring a uniform indentation shift (the replacement is re-indented).
The SEARCH text must match exactly one location. Blocks are applied in order; nothing is written unless all blocks apply.
Stdlib only.
"""
import argparse
import os
import re
import sys

def _find_root():
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


ROOT = _find_root()
BLOCK_RE = re.compile(
    r"(?P<path>[^\n<=>]*?)\s*\n?<{5,9}\s*SEARCH[^\n]*\n(?P<search>.*?)\n?={5,9}[^\n]*\n(?P<replace>.*?)\n?>{5,9}\s*REPLACE",
    re.S,
)


def normalize_payload(s):
    s = s.strip()
    s = re.sub(r"^```[a-zA-Z]*\n|\n?```$", "", s)  # code fences
    s = s.strip("`").rstrip()  # stray backticks from the tool-call slip
    if "\n" not in s and "\\n" in s:  # model double-escaped the newlines
        s = s.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")
    return s


def _strip_indent(lines):
    ind = min((len(l) - len(l.lstrip(" ")) for l in lines if l.strip()), default=0)
    return [l[ind:] if l.strip() else "" for l in lines], ind


def find(content, search):
    """Return (start, end, strategy) char offsets of the unique match, or an error message."""
    n = content.count(search)
    if n == 1:
        i = content.index(search)
        return i, i + len(search), "exact"
    if n > 1:
        return f"SEARCH text matches {n} places; add surrounding lines to make it unique"
    lines = content.split("\n")
    s_lines = search.split("\n")
    while s_lines and not s_lines[-1].strip():
        s_lines.pop()
    while s_lines and not s_lines[0].strip():
        s_lines.pop(0)
    if not s_lines:
        return "SEARCH text is empty after trimming"
    k = len(s_lines)
    offs = [0]
    for l in lines:
        offs.append(offs[-1] + len(l) + 1)
    for strategy, key in (("rstrip", lambda ls: [l.rstrip() for l in ls]),
                          ("indent", lambda ls: [l.rstrip() for l in _strip_indent(ls)[0]])):
        target = key(s_lines)
        hits = [i for i in range(len(lines) - k + 1) if key(lines[i:i + k]) == target]
        if len(hits) == 1:
            i = hits[0]
            return offs[i], offs[i + k] - 1, strategy
        if len(hits) > 1:
            return f"SEARCH text matches {len(hits)} places (ignoring whitespace); add surrounding lines to make it unique"
    # Show the closest real lines so the model can copy them verbatim without another read.
    import difflib
    want = "\n".join(l.strip() for l in s_lines)
    best, best_i = 0.0, -1
    firsts = sorted(range(len(lines)), key=lambda i: -difflib.SequenceMatcher(None, lines[i].strip(), s_lines[0].strip()).quick_ratio())[:40]
    for i in firsts:
        r = difflib.SequenceMatcher(None, "\n".join(l.strip() for l in lines[i:i + k]), want).ratio()
        if r > best:
            best, best_i = r, i
    if best_i >= 0 and best > 0.5:
        shown = lines[best_i:best_i + min(k, 15)]
        return ("SEARCH text not found. The closest lines in the file are lines %d-%d (similarity %.2f); copy SEARCH "
                "from them exactly:\n----\n%s\n----" % (best_i + 1, best_i + len(shown), best, "\n".join(shown)))
    return ("SEARCH text not found and nothing similar exists in this file: check the file path, then re-read the "
            "file with sed -n 'A,Bp' FILE.")


def unescape(s):
    """Undo the model's JSON-style over-escaping inside an otherwise multi-line block (\\" -> ", \\' -> ', \\\\ -> \\)."""
    return s.replace('\\"', '"').replace("\\'", "'").replace("\\t", "\t").replace("\\\\", "\\")


def reindent(replace, matched, search):
    """When matched with an indentation shift, shift the replacement by the same amount."""
    m_ind = _strip_indent(matched.split("\n"))[1]
    s_ind = _strip_indent(search.strip("\n").split("\n"))[1]
    d = m_ind - s_ind
    if d == 0:
        return replace
    out = []
    for l in replace.split("\n"):
        if not l.strip():
            out.append("")
        elif d > 0:
            out.append(" " * d + l)
        else:
            cut = min(-d, len(l) - len(l.lstrip(" ")))
            out.append(l[cut:])
    return "\n".join(out)


def _remember_failure(payload):
    import hashlib
    memo = os.path.join("/tmp" if os.path.isdir("/workspace") else (os.environ.get("TMPDIR") or "/tmp"), ".apply_edit_failed")
    try:
        with open(memo, "a") as f:
            f.write(hashlib.sha1(payload.encode("utf-8", "replace")).hexdigest() + "\n")
    except (IOError, OSError):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit", default=None, help="one or more SEARCH/REPLACE blocks (run_skill_script key 'edit')")
    ap.add_argument("--file", default=None, help="optional default path when a block has no path line")
    ap.add_argument("edit_file", nargs="?", default=None, help="read blocks from this file ('-' = stdin)")
    a, extra = ap.parse_known_args(argv)
    if a.edit is not None:
        raw = a.edit + ((" " + " ".join(extra)) if extra else "")
    elif a.edit_file in (None, "-"):
        raw = sys.stdin.read()
    else:
        raw = open(_tmp(a.edit_file), encoding="utf-8").read()
    payload = normalize_payload(raw)
    import hashlib
    memo = os.path.join("/tmp" if os.path.isdir("/workspace") else (os.environ.get("TMPDIR") or "/tmp"), ".apply_edit_failed")
    digest = hashlib.sha1(payload.encode("utf-8", "replace")).hexdigest()
    try:
        seen = set(open(memo).read().split())
    except (IOError, OSError):
        seen = set()
    if digest in seen:
        print("FAIL: this exact edit already failed before. Do NOT resend it: copy SEARCH from the closest lines shown "
              "in the previous FAIL message (or re-read the file), or change approach.")
        return 1
    blocks = list(BLOCK_RE.finditer(payload))
    if not blocks:
        print("FAIL: no SEARCH/REPLACE block found. Format:\npath/to/file.py\n<<<<<<< SEARCH\n<exact current lines>\n"
              "=======\n<new lines>\n>>>>>>> REPLACE")
        return _remember_failure(payload) or 1
    files = {}
    log = []
    for n, b in enumerate(blocks, 1):
        path = (b["path"].strip().strip("`'\"").splitlines() or [""])[-1].strip() or (a.file or "")
        if not path:
            print(f"FAIL block {n}: missing file path line before <<<<<<< SEARCH")
            return _remember_failure(payload) or 1
        if path.startswith("/workspace/"):
            path = path[len("/workspace/"):]
        rel = os.path.relpath(os.path.join(ROOT, path), ROOT) if not os.path.isabs(path) else os.path.relpath(path, ROOT)
        if rel.startswith(".."):
            print(f"FAIL block {n}: path {path} is outside the repository")
            return _remember_failure(payload) or 1
        full = os.path.join(ROOT, rel)
        if rel not in files:
            files[rel] = open(full, encoding="utf-8").read() if os.path.exists(full) else None
        content, search, replace = files[rel], b["search"], b["replace"]
        if not search.strip():
            if content:
                print(f"FAIL block {n}: empty SEARCH but {rel} already has content; give the lines to replace")
                return _remember_failure(payload) or 1
            files[rel] = replace if replace.endswith("\n") else replace + "\n"
            log.append(f"block {n}: created {rel}")
            continue
        if content is None:
            print(f"FAIL block {n}: {rel} does not exist")
            return _remember_failure(payload) or 1
        r = find(content, search)
        if isinstance(r, str) and unescape(search) != search:  # model over-escaped quotes: retry, and unescape REPLACE too
            r2 = find(content, unescape(search))
            if not isinstance(r2, str):
                r, search, replace = r2, unescape(search), unescape(replace)
                r = (r[0], r[1], r[2] + "+unescape")
        if isinstance(r, str):
            print(f"FAIL block {n} ({rel}): {r}")
            return _remember_failure(payload) or 1
        i, j, strategy = r
        new = replace if not strategy.startswith("indent") else reindent(replace, content[i:j], search)
        files[rel] = content[:i] + new + content[j:]
        line = content[:i].count("\n") + 1
        log.append(f"block {n}: {rel} line {line} ({strategy} match, -{content[i:j].count(chr(10)) + 1}/+{new.count(chr(10)) + 1} lines)")
    bad = []
    for rel, content in files.items():  # refuse edits that break a file that compiled before
        if not rel.endswith(".py"):
            continue
        try:
            compile(content, rel, "exec")
        except SyntaxError as e:
            full = os.path.join(ROOT, rel)
            try:
                compile(open(full, encoding="utf-8").read(), rel, "exec") if os.path.exists(full) else None
            except SyntaxError:
                continue  # file was already broken; do not block a repair attempt
            bad.append(f"{rel} line {e.lineno}: {e.msg}: {(e.text or '').rstrip()}")
    if bad:
        print("FAIL: edit NOT applied, it would introduce a syntax error (check indentation/brackets):\n" + "\n".join(bad))
        return _remember_failure(payload) or 2
    for rel, content in files.items():  # all blocks applied in memory: write
        full = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        open(full, "w", encoding="utf-8").write(content)
    print("\n".join(log))
    print("OK: applied; syntax check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build a proxy benchmark of unseen-repo tasks that mimics the organizers' curation.

Candidate = first-parent commit on the default branch that corresponds to a merged GitHub PR
(squash "Title (#N)" or "Merge pull request #N"), created >= SINCE, whose diff touches >=1
non-test .py source file AND >=1 test .py file, small-to-medium (<= MAX_SRC_FILES source files,
<= MAX_SRC_CHURN changed source lines). Split exactly like the public tasks:
  patch      = non-test .py hunks only (public tasks: 278/278 patch files are .py)
  test_patch = test .py hunks only (tests/... like the public tasks)
problem_statement = PR title + "\n\n" + PR body (scraped from the GitHub PR page; the public
tasks use the same "title\n\nbody" layout), hints_text = "".
instance_id = <repo short name>_<PR#> (public naming).

Snapshots: fresh single-commit git repo of the tree at base_commit (first parent), tar.gz,
like src/mining/build_snapshots.py (read-tree instead of `git archive` so export-ignore'd
tests are kept).

Usage:
  .venv/bin/python -m src.analysis.hidden.mine_proxy --per-repo 20
-> data/derived/proxy/{candidates.jsonl,tasks.jsonl,snapshots/<id>.tgz}
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from unidiff import PatchSet

ROOT = Path(__file__).resolve().parents[3]
PROXY = ROOT / "data" / "derived" / "proxy"
REPOS_DIR = PROXY / "repos"
SNAP = PROXY / "snapshots"
CACHE = PROXY / "pr_pages"

# GitHub slug -> local clone dir. Slugs are the canonical (post-rename) names.
REPOS = {
    "pallets/flask": "flask",
    "pallets/click": "click",
    "pallets/werkzeug": "werkzeug",
    "pallets/jinja": "jinja",
    "fastapi/typer": "typer",
    "fastapi/sqlmodel": "sqlmodel",
    "Kludex/starlette": "starlette",
    "tqdm/tqdm": "tqdm",
    "requests/requests-oauthlib": "requests-oauthlib",
    "marshmallow-code/marshmallow": "marshmallow",
    "python-attrs/attrs": "attrs",
    "jd/tenacity": "tenacity",
    "andialbrecht/sqlparse": "sqlparse",
}
# Google repos exported from the internal monorepo by Copybara: each commit carries
# "PiperOrigin-RevId: <CL>". The hidden-set harness keys tasks by CL (swegemma.deduplication.get_task_cl)
# and supports Google test conventions (*_test.py, *Test classes, fake_gfile), so these are the closest
# public analogue of "private repositories". Task = one CL; statement = CL description.
GOOGLE = {
    "google/adk-python": "adk-python",
    "google/pyglove": "pyglove",
    "google/fiddle": "fiddle",
    "google/ml_collections": "ml_collections",
    "google/etils": "etils",
}
REPOS.update(GOOGLE)
SKIP_CL = re.compile(r"internal change|no public description|automated code change|copybara|"
                     r"rollback|roll back|revert|presubmit|pytype|BUILD", re.I)
SINCE = "2023-01-01"
MAX_SRC_FILES, MAX_SRC_CHURN, MAX_TEST_CHURN = 4, 250, 600
SKIP_SUBJ = re.compile(
    r"\b(bump|release|pre-commit|pre-commit-ci|typo|lint|ruff|mypy|ci\b|docs?\b|readme|changelog|"
    r"dependabot|format|black|isort|update release notes|start version|merge branch|stable)\b", re.I)
FIELDS = ["instance_id", "repo", "base_commit", "patch", "test_patch", "problem_statement", "hints_text", "created_at"]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          errors="replace").stdout


def is_test(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    parts = path.split("/")
    return base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py" or any(
        p in ("tests", "test", "testing") for p in parts[:-1])


def is_src(path: str) -> bool:
    return path.endswith(".py") and not is_test(path) and not path.startswith(
        ("docs/", "docs_src/", "examples/", "scripts/", "benchmarks/", "artwork/", ".github/"))


def pr_number(subj: str, body: str) -> int | None:
    m = re.match(r"Merge pull request #(\d+)", subj)
    if m:
        return int(m.group(1))
    m = re.search(r"\(#(\d+)\)\s*$", subj)
    if m:
        return int(m.group(1))
    return None


def strip_unidiff(pf) -> str:
    """Render a PatchedFile as '--- a/x\n+++ b/x\n@@...' (public task style, no `diff --git`)."""
    src = pf.source_file if pf.source_file != "/dev/null" else "/dev/null"
    tgt = pf.target_file if pf.target_file != "/dev/null" else "/dev/null"
    return f"--- {src}\n+++ {tgt}\n" + "".join(str(h) for h in pf)


def html_to_md(s: str) -> str:
    s = re.sub(r"<pre[^>]*>(.*?)</pre>", lambda m: "\n```\n" + re.sub(r"<[^>]+>", "", m.group(1)) + "\n```\n", s,
               flags=re.S)
    s = re.sub(r"<code[^>]*>(.*?)</code>", lambda m: "`" + re.sub(r"<[^>]+>", "", m.group(1)) + "`", s, flags=re.S)
    s = re.sub(r"<li[^>]*>", "\n- ", s)
    s = re.sub(r"<h(\d)[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", s)
    s = re.sub(r"<br\s*/?>|</p>|</h\d>|</li>|</ul>|</ol>|</blockquote>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _balanced_div(s: str, j: int) -> str:
    """Inner HTML of the element whose opening tag ends at j (balanced <div>/</div> count)."""
    depth, pos = 1, j
    for m in re.finditer(r"<(/?)div\b", s[j:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return s[j:j + m.start()]
    return s[j:j + 20000]


def parse_pr_html(s: str) -> tuple[str, str]:
    m = re.search(r"<title>(.*?)</title>", s, re.S)
    title = html.unescape(m.group(1)) if m else ""
    title = re.sub(r"\s+by\s+\S+\s+·\s+Pull Request #\d+.*$", "", title, flags=re.S).strip()
    body = ""
    i = s.find("comment-body markdown-body")
    if i >= 0:
        j = s.find(">", i) + 1
        body = html_to_md(_balanced_div(s, j))
        body = re.sub(r"^\s*No description provided\.\s*$", "", body).strip()
        body = re.sub(r"\n[^\n]*Summary by cubic.*$", "", body, flags=re.S).strip()
    return title, body


def fetch_pr(slug: str, num: int) -> tuple[str, str] | None:
    """(title, body) scraped from the PR page (raw HTML cached). None on failure."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cp = CACHE / f"{slug.replace('/', '__')}_{num}.html"
    if not cp.exists():
        url = f"https://github.com/{slug}/pull/{num}"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 proxy-bench"})
                cp.write_text(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace"))
                break
            except Exception:  # noqa: BLE001
                time.sleep(5 * (attempt + 1))
        else:
            return None
        time.sleep(1.0)
    return parse_pr_html(cp.read_text())


def mine_repo(slug: str, short: str, per_repo: int) -> list[dict]:
    repo = REPOS_DIR / short
    # all branches reachable from HEAD (pallets merge PRs into `stable` first); squash commits
    # "(#N)" are diffed against their parent, "Merge pull request #N" against the first parent.
    log = git(repo, "log", f"--since={SINCE}", "--format=%H%x1f%P%x1f%cI%x1f%s%x1f%b%x1e")
    rows = []
    seen: set[int] = set()
    for rec in log.split("\x1e"):
        rec = rec.strip()
        if not rec:
            continue
        sha, parents, cdate, subj, body = (rec.split("\x1f") + [""] * 5)[:5]
        if slug in GOOGLE:
            m = re.search(r"PiperOrigin-RevId:\s*(\d+)", body)
            num = int(m.group(1)) if m else None
            if num is None or len(parents.split()) != 1 or SKIP_CL.search(subj):
                continue
        else:
            num = pr_number(subj, body)
        if num is None or num in seen:
            continue
        seen.add(num)
        title_guess = body.strip().splitlines()[0] if subj.startswith("Merge pull request") and body.strip() else subj
        if SKIP_SUBJ.search(title_guess):
            continue
        base = parents.split()[0]
        diff = git(repo, "diff", "--no-color", "--no-renames", base, sha)
        try:
            ps = PatchSet(diff)
        except Exception:  # noqa: BLE001
            continue
        src = [f for f in ps if is_src(f.path)]
        tst = [f for f in ps if f.path.endswith(".py") and is_test(f.path)]
        if not src or not tst or len(src) > MAX_SRC_FILES:
            continue
        if any(f.is_binary_file for f in src + tst):
            continue
        src_churn = sum(f.added + f.removed for f in src)
        tst_churn = sum(f.added + f.removed for f in tst)
        if src_churn > MAX_SRC_CHURN or tst_churn > MAX_TEST_CHURN or src_churn == 0:
            continue
        rows.append({
            "instance_id": f"{short.replace('-', '_')}_{num}", "repo": slug, "base_commit": base, "commit": sha,
            "patch": "".join(strip_unidiff(f) for f in src), "test_patch": "".join(strip_unidiff(f) for f in tst),
            "hints_text": "", "created_at": cdate, "subject": title_guess, "commit_body": body,
            "src_files": len(src), "src_churn": src_churn,
        })
        if len(rows) >= per_repo:
            break
    return rows


def build_snapshot(row: dict) -> bool:
    short = REPOS[row["repo"]]
    tgz = SNAP / f"{row['instance_id']}.tgz"
    if tgz.exists():
        return True
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", "/tmp")) as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(td) / "idx"))
        r = subprocess.run(["git", "--git-dir", str(REPOS_DIR / short / ".git"), "--work-tree", str(ws),
                            "read-tree", "--reset", "-u", row["base_commit"]], env=env, capture_output=True)
        if r.returncode != 0:
            return False
        cfg = ["-c", "user.email=agent@eval", "-c", "user.name=Agent", "-c", "init.defaultBranch=main"]
        subprocess.run(["git", *cfg, "init", "-q", str(ws)], check=True)
        r = subprocess.run(["git", *cfg, "-C", str(ws), "add", "-A"], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"snapshot failed {row['instance_id']}: {r.stderr[-300:]}", flush=True)
            return False
        subprocess.run(["git", *cfg, "-C", str(ws), "commit", "-qm", "base"], check=True)
        subprocess.run(["tar", "czf", str(tgz), "-C", str(ws), "."], check=True)
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-repo", type=int, default=20)
    ap.add_argument("--repos", nargs="*", default=[r for r in REPOS if r not in GOOGLE])
    ap.add_argument("--suffix", default="", help="write candidates<suffix>.jsonl / tasks<suffix>.jsonl")
    a = ap.parse_args()
    SNAP.mkdir(parents=True, exist_ok=True)
    cands = []
    for slug in a.repos:
        rs = mine_repo(slug, REPOS[slug], a.per_repo)
        print(f"{slug}: {len(rs)} candidates", flush=True)
        cands += rs
    for r in cands:  # sequential + polite: ~1 req/s
        if r["repo"] in GOOGLE:  # CL description = commit message without trailers
            body = re.sub(r"^(PiperOrigin-RevId|COPYBARA_INTEGRATE_REVIEW|GitOrigin-RevId|FUTURE_COPYBARA_INTEGRATE_REVIEW|"
                          r"Merge-Request|Co-authored-by|Change-Id):.*$", "", r["commit_body"], flags=re.M | re.I).strip()
            r["problem_statement"] = (r["subject"] + ("\n\n" + body if body else "")).strip()
            r["statement_source"] = "cl_description"
            continue
        pr = fetch_pr(r["repo"], int(r["instance_id"].rsplit("_", 1)[1]))
        title, body = pr if pr and pr[0] else (r["subject"], "")
        r["problem_statement"] = (title + ("\n\n" + body if body else "")).strip()
        r["statement_source"] = "pr_page" if pr and pr[0] else "commit"
    with ThreadPoolExecutor(int(os.environ.get("SNAP_WORKERS", "8"))) as ex:
        ok = list(ex.map(build_snapshot, cands))
    with open(PROXY / f"candidates{a.suffix}.jsonl", "w") as f:
        for r in cands:
            f.write(json.dumps(r) + "\n")
    with open(PROXY / f"tasks{a.suffix}.jsonl", "w") as f:
        for r, good in zip(cands, ok):
            if good:
                f.write(json.dumps({k: r[k] for k in FIELDS}) + "\n")
    print(f"tasks: {sum(ok)}/{len(cands)} -> {PROXY / f'tasks{a.suffix}.jsonl'}")


if __name__ == "__main__":
    main()

---
name: repo-tools
description: Fast code search and verification for the repository in /workspace. locate.py ranks the functions/classes most relevant to an issue; show.py prints a definition with line numbers; tests.py finds tests mentioning a name; check.py compiles your changes and runs a targeted pytest with a compact verdict.
---

# repo-tools

Run with `run_skill_script` (skill_name `repo-tools`). Each call takes about a second and does not use your tool-call budget.

| script | args | use it to |
|---|---|---|
| `scripts/locate.py` | `{"query": "<issue title + key identifiers + error text>"}` | find where to edit (ranked `file:lines qualname`) |
| `scripts/show.py` | `{"name": "Class.method"}` (optional `"file"`) | print a definition with line numbers before editing |
| `scripts/tests.py` | `{"name": "identifier"}` | find existing tests to run |
| `scripts/check.py` | `{"tests": "tests/test_x.py -k name"}` | after editing: compile changed files, list untracked files, run tests |

---
name: patch-check
description: One-call pre-submit check of /workspace. Lists changed files, removes scratch files, reverts test/config edits, syntax- and import-checks changed modules, runs /tmp/repro.py on the ORIGINAL and the patched code, optionally runs pytest, lists sibling implementations and call sites of changed functions, and prints VERDICT OK or FAIL.
---

# patch-check

Run it once, after the fix and before `submit_patch`: run_skill_script with skill_name patch-check, file_path scripts/check.py, args {tests: "<closest test file> -k <keyword>"} (args may be omitted).

- `REPRO: original=FAIL patched=PASS` is real evidence that the fix works.
- `original=PASS` means /tmp/repro.py does not reproduce the bug, so it is not evidence. Rely on reading the code instead.
- `patched=FAIL` means the fix does not work.
- `SIBLINGS/CALLERS` lists other functions with the same name and the places that call the changed function. Check whether the same bug exists there too.
- `VERDICT: FAIL (...)` lists the concrete problems (empty patch, syntax error, import error, or repro still failing).

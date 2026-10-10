---
name: apply-edit
description: The ONLY way to modify existing source files. Applies one or more SEARCH/REPLACE blocks given as a single text argument, refuses edits that would break Python syntax, and reports exactly what changed.
---

# apply-edit

Run it with run_skill_script: skill_name apply-edit, file_path scripts/apply_edit.py, args with a single key edit set to the blocks below.

```
path/to/file.py
<<<<<<< SEARCH
exact lines currently in the file (with their indentation)
=======
the new lines
>>>>>>> REPLACE
```

- Put the file path (relative to /workspace) on the line before each `<<<<<<< SEARCH`. Several blocks may follow each other; all are applied or none.
- SEARCH must match exactly one place. Copy it from fresh `sed -n` output, without line numbers. 2-6 lines is usually enough to be unique.
- Output `OK: applied; syntax check passed` means the edit is in the file. `FAIL ...` means nothing was changed: read the message (not found / ambiguous / syntax error), re-read the lines, and send a corrected block.
- An empty SEARCH section creates a new file.

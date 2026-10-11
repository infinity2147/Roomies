---
name: edit-engine
description: Installs the file-edit engine /tmp/ae.py. Run once per task, before your first edit.
---

# edit-engine

Install once: run_skill_script with skill_name edit-engine and file_path scripts/install.py (no args).

Then make every source edit with run_command:

```
python3 /tmp/ae.py <<'AE_EOF'
path/to/file.py
<<<<<<< SEARCH
exact lines currently in the file
=======
new lines
>>>>>>> REPLACE
AE_EOF
```

Several blocks may follow each other (all or nothing). SEARCH must match one place; whitespace and indentation differences are tolerated. The engine refuses edits that break Python syntax, shows the closest real lines when SEARCH is not found, and refuses an identical retry of a failed edit.

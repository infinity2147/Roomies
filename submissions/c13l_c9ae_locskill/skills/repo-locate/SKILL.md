---
name: repo-locate
description: One-shot code localizer for the repository in /workspace. Given the issue text, returns a ranked list of candidate files with the line ranges and signatures of the functions/classes that match the issue's identifiers, error messages and paths.
---

# repo-locate

Run it with run_skill_script: skill_name repo-locate, file_path scripts/locate.py, args with key issue set to the issue text (title, identifiers, error message, file names; plain text, no backticks needed).
Optional key hints: file paths or Class.method names you already suspect.

Output (at most ~25 lines): numbered files, best first; under each file the matching definitions as
`L<start>-<end> <qualname>: <signature> [hit lines ...]`, then related test files.
Read only the top 1-2 ranges with `sed -n 'START,ENDp' FILE`. Run it once per task; do not re-run with the same text.

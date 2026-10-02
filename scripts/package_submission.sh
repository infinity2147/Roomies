#!/usr/bin/env bash
# Validate a submission dir with the organizers' compiler and build submission.zip (agent.yaml at root).
# Usage: scripts/package_submission.sh submissions/c4 [out.zip]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUB="$(realpath "$1")"; OUT="${2:-$ROOT/results/$(basename "$SUB")_submission.zip}"
find "$SUB" -name __pycache__ -type d -prune -exec rm -rf {} +
cd "$ROOT" && .venv-eval/bin/python -m src.eval.validate_submission "$SUB" | tail -3
rm -f "$OUT"
.venv/bin/python -c "import sys,zipfile,pathlib; s=pathlib.Path(sys.argv[1]); z=zipfile.ZipFile(sys.argv[2],'w',zipfile.ZIP_DEFLATED); [z.write(p,p.relative_to(s).as_posix()) for p in sorted(s.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]; z.close()" "$SUB" "$OUT"
.venv/bin/python -c "import sys,zipfile; [print(i.filename, i.file_size) for i in zipfile.ZipFile(sys.argv[1]).infolist()]" "$OUT"
echo "wrote $OUT"

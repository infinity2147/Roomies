#!/usr/bin/env bash
# Copy the project + this Claude Code session to another machine (e.g. IITB Prajna) with rsync over ssh.
# Run on the OLD machine. Re-runnable: rsync only transfers what changed and resumes partial files.
#
# Usage: scripts/migrate/push_to_prajna.sh <user@host> <remote_project_dir>
#   e.g. scripts/migrate/push_to_prajna.sh 24b4518@prajna.iitb.ac.in /home/24b4518/projects/Gemma_RL
# Notes:
# - Virtual envs are NOT copied (rebuild with scripts/migrate/setup_env.sh on the new machine).
# - The 21 GB competition zip is NOT copied (data/ is already extracted). Add --with-zip to copy it.
# - Snapshots (21 GB) + model (22 GB) dominate; ~55 GB total.
set -euo pipefail
DEST="$1"; RDIR="$2"; WITH_ZIP="${3:-}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
EXCL=(--exclude '.venv/' --exclude '.venv-harness/' --exclude '.venv-eval/' --exclude '__pycache__/'
      --exclude '*.pyc' --exclude 'external/python/' --exclude 'results/kaggle_kernels/*/kernel.py')
[[ "$WITH_ZIP" == "--with-zip" ]] || EXCL+=(--exclude 'data/gemma-4-developer-agent.zip')

ssh "$DEST" "mkdir -p '$RDIR'"
# 1) code + git history first (small), then the big data
rsync -aHP --partial "${EXCL[@]}" --exclude 'data/' --exclude 'external/' ./ "$DEST:$RDIR/"
rsync -aHP --partial "${EXCL[@]}" data external "$DEST:$RDIR/"

# 2) Claude Code session + memory. Claude keys sessions by the project's absolute path with every
#    non-alphanumeric char replaced by '-'.
OLD_KEY="$(echo "$ROOT" | sed 's/[^A-Za-z0-9]/-/g')"
NEW_KEY="$(echo "$RDIR" | sed 's/[^A-Za-z0-9]/-/g')"
ssh "$DEST" "mkdir -p ~/.claude/projects/$NEW_KEY"
rsync -aP "$HOME/.claude/projects/$OLD_KEY/" "$DEST:~/.claude/projects/$NEW_KEY/"

# 3) Kaggle token (optional; skip if you prefer to create a fresh one on the new machine)
if [[ -f "$HOME/.kaggle/access_token" ]]; then
  ssh "$DEST" "mkdir -p ~/.kaggle && chmod 700 ~/.kaggle"
  rsync -a "$HOME/.kaggle/access_token" "$DEST:~/.kaggle/access_token"
  ssh "$DEST" "chmod 600 ~/.kaggle/access_token"
fi
echo "Done. On the new machine: cd $RDIR && scripts/migrate/setup_env.sh && claude --resume"

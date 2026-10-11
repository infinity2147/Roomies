"""Install the edit engine at /tmp/ae.py (as seen by run_command) so edits go through the single-argument run_command tool."""
import os
import shutil
import sys

here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "scripts"
src = os.path.join(here, "apply_edit.py")
if not os.path.exists(src):
    src = os.path.join("scripts", "apply_edit.py")
tmp = "/tmp" if os.path.isdir("/workspace") else (os.environ.get("TMPDIR") or "/tmp")
dst = os.path.join(tmp, "ae.py")
shutil.copyfile(src, dst)
print("installed %s. Edit with run_command:\npython3 /tmp/ae.py <<'AE_EOF'\npath/to/file.py\n<<<<<<< SEARCH\n<exact current lines>\n=======\n<new lines>\n>>>>>>> REPLACE\nAE_EOF" % "/tmp/ae.py")
sys.stdout.flush()

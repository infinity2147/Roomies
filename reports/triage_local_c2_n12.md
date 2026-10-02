# Triage: local_c2_n12

resolved 0/12 (0.0%); mean time 495s; max 508s

Buckets: agent_error=12

Tool usage: run_command=10, skill:locate.py`,skill_name:=6, skill:locate.py"=3, read_file=3, write_file=2, list_skills=1

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| requests_7433 | agent_error | 494 | 0 |  | src/requests/models.py | skill:locate.py`,skill_name:=3 | Agent exceeded session timeout (8.0 min) |
| rich_4006 | agent_error | 486 | 0 |  | rich/cells.py | skill:locate.py`,skill_name:=3 | Agent exceeded session timeout (8.0 min) |
| fastapi_14512 | agent_error | 508 | 2 |  | fastapi/_compat/v2.py | write_file=1 run_command=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14485 | agent_error | 503 | 0 |  | fastapi/dependencies/utils.py |  | Agent exceeded session timeout (8.0 min) |
| fastapi_14458 | agent_error | 503 | 0 |  | fastapi/dependencies/models.py |  | Agent exceeded session timeout (8.0 min) |
| fastapi_9555 | agent_error | 502 | 0 |  | fastapi/dependencies/models.py |  | Agent exceeded session timeout (8.0 min) |
| rich_3944 | agent_error | 486 | 1 |  | rich/cells.py | run_command=1 | Agent exceeded session timeout (8.0 min) |
| rich_3930 | agent_error | 485 | 1 |  | rich/__main__.py, rich/_cell_widths.py, rich/cells.py | run_command=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14583 | agent_error | 504 | 1 |  | fastapi/dependencies/utils.py, fastapi/routing.py | run_command=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_11194 | agent_error | 498 | 5 |  | fastapi/dependencies/utils.py | run_command=4 write_file=1 | Agent exceeded session timeout (8.0 min) |
| rich_3468 | agent_error | 484 | 1 |  | rich/console.py | skill:locate.py"=3 run_command=1 list_skills=1 | Agent exceeded session timeout (8.0 min) |
| rich_3471 | agent_error | 484 | 4 |  | rich/text.py | read_file=3 run_command=1 | Agent exceeded session timeout (8.0 min) |

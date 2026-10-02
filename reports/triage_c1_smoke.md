# Triage: c1_smoke

resolved 1/8 (12.5%); mean time 383s; max 495s

Buckets: right_file_wrong_fix=4, agent_error=2, resolved=1, wrong_location=1

Tool usage: run_command=78, read_file=54, edit_file=14, write_file=12, skill:locate.py=9, skill:show.py=8, skill:show.py`,skill_name:=5, submit_patch=4, skill:?=1, show_definition=1

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| fastapi_15589 | resolved | 495 | 29 | fastapi/dependencies/utils.py, repro.py, repro_model.py | fastapi/dependencies/utils.py | run_command=12 read_file=12 write_file=4 edit_file=1 |  |
| fastapi_15030 | right_file_wrong_fix | 462 | 21 | fastapi/responses.py | fastapi/openapi/utils.py, fastapi/responses.py, fastapi/rout | run_command=10 read_file=5 edit_file=5 write_file=1 submit_patch=1 |  |
| rich_4075 | agent_error | 484 | 33 |  | rich/console.py | read_file=13 run_command=10 skill:show.py=8 skill:show.py`,skill_name:=5 skill:locate.py=2 | Agent exceeded session timeout (8.0 min) |
| fastapi_14448 | right_file_wrong_fix | 492 | 13 | fastapi/dependencies/models.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=6 skill:locate.py=2 read_file=2 edit_file=2 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14430 | wrong_location | 489 | 15 | fastapi/_compat/shared.py | fastapi/_compat/v2.py | run_command=6 skill:locate.py=5 edit_file=2 skill:?=1 read_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_13207 | right_file_wrong_fix | 380 | 39 | fastapi/_compat/v2.py | fastapi/_compat/v2.py | run_command=20 read_file=14 edit_file=3 write_file=2 submit_patch=2 |  |
| rich_3944 | agent_error | 122 | 8 |  | rich/cells.py | run_command=6 read_file=2 show_definition=1 | Sandbox execution error: Tool 'show_definition' not found.
A |
| fastapi_14953 | right_file_wrong_fix | 141 | 17 | fastapi/datastructures.py | fastapi/_compat/v2.py, fastapi/datastructures.py | run_command=8 read_file=5 write_file=3 edit_file=1 submit_patch=1 |  |

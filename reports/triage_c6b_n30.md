# Triage: c6b_n30

resolved 9/30 (30.0%); mean time 420s; max 517s

Buckets: right_file_wrong_fix=10, resolved=9, agent_error=7, wrong_location=2, touched_tests_only=2

Tool usage: run_command=483, read_file=373, edit_file=134, write_file=27, submit_patch=13, skill:check.py`,skill_name:=8, skill:check.py=7, get_status=7, skill:locate.py=3, skill:tests.py=3

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| fastapi_15661 | wrong_location | 455 | 37 | scripts/release.py | scripts/prepare_release.py | run_command=18 read_file=12 edit_file=4 write_file=2 skill:locate.py=1 |  |
| fastapi_15589 | agent_error | 486 | 29 |  | fastapi/dependencies/utils.py | read_file=15 run_command=13 write_file=1 | Agent exceeded session timeout (8.0 min) |
| requests_7309 | right_file_wrong_fix | 383 | 29 | src/requests/utils.py | src/requests/utils.py | run_command=16 read_file=8 skill:check.py`,skill_name:=8 skill:check.py=3 write_file=1 |  |
| rich_4077 | resolved | 485 | 33 | rich/file_proxy.py | rich/file_proxy.py | run_command=21 read_file=9 edit_file=2 write_file=1 get_status=1 |  |
| rich_4076 | wrong_location | 485 | 38 | rich/pretty.py | rich/ansi.py | run_command=21 read_file=14 write_file=1 edit_file=1 skill:check.py=1 | Agent exceeded session timeout (8.0 min) |
| rich_4075 | agent_error | 482 | 38 |  | rich/console.py | read_file=21 run_command=16 edit_file=6 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14258 | right_file_wrong_fix | 488 | 42 | fastapi/routing.py, repro.py | fastapi/routing.py | read_file=25 run_command=14 edit_file=7 write_file=2 | Agent exceeded session timeout (8.0 min) |
| fastapi_14786 | resolved | 257 | 15 | fastapi/security/utils.py | fastapi/security/utils.py | run_command=9 read_file=3 write_file=1 edit_file=1 skill:tests.py=1 |  |
| fastapi_14492 | resolved | 229 | 19 | docs_src/metadata/tutorial001_1_py39.py | docs_src/metadata/tutorial001_1_py39.py | run_command=11 read_file=6 edit_file=1 skill:check.py=1 submit_patch=1 |  |
| fastapi_14306 | right_file_wrong_fix | 488 | 43 | fastapi/exceptions.py, fastapi/routing.py | fastapi/exceptions.py, fastapi/routing.py | edit_file=26 read_file=23 run_command=14 | Agent exceeded session timeout (8.0 min) |
| fastapi_14448 | touched_tests_only | 517 | 27 |  | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=14 read_file=10 edit_file=7 write_file=3 | Agent exceeded session timeout (8.0 min) |
| fastapi_14430 | agent_error | 484 | 35 |  | fastapi/_compat/v2.py | run_command=27 read_file=8 | Agent exceeded session timeout (8.0 min) |
| fastapi_14419 | agent_error | 484 | 22 |  | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=11 read_file=11 | Agent exceeded session timeout (8.0 min) |
| fastapi_14301 | resolved | 259 | 19 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=12 read_file=5 edit_file=1 write_file=1 get_status=1 |  |
| fastapi_14246 | agent_error | 484 | 39 |  | fastapi/_compat/v2.py | run_command=21 read_file=18 | Agent exceeded session timeout (8.0 min) |
| fastapi_13713 | right_file_wrong_fix | 487 | 49 | fastapi/applications.py, fastapi/openapi/utils.py | fastapi/applications.py, fastapi/openapi/utils.py | read_file=25 run_command=18 edit_file=13 write_file=1 get_status=1 | Agent exceeded session timeout (8.0 min) |
| httpx_3672 | right_file_wrong_fix | 372 | 19 | src/httpx/_network.py, src/httpx/_parsers.py, src/httpx/_ser | src/ahttpx/_parsers.py, src/ahttpx/_pool.py, src/ahttpx/_ser | read_file=11 edit_file=5 run_command=3 submit_patch=1 |  |
| fastapi_15800 | right_file_wrong_fix | 427 | 47 | fastapi/applications.py, fastapi/routing.py | fastapi/applications.py, fastapi/routing.py | run_command=25 read_file=19 edit_file=2 write_file=1 submit_patch=1 |  |
| fastapi_14371 | right_file_wrong_fix | 493 | 28 | fastapi/params.py | fastapi/_compat/v2.py, fastapi/dependencies/utils.py, fastap | run_command=12 read_file=10 edit_file=4 skill:tests.py=1 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14605 | right_file_wrong_fix | 489 | 36 | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | edit_file=41 read_file=17 run_command=14 | Agent exceeded session timeout (8.0 min) |
| fastapi_13537 | resolved | 252 | 11 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=6 read_file=4 edit_file=1 submit_patch=1 |  |
| fastapi_14953 | touched_tests_only | 491 | 43 |  | fastapi/_compat/v2.py, fastapi/datastructures.py | read_file=21 run_command=20 write_file=2 | Agent exceeded session timeout (8.0 min) |
| fastapi_14616 | right_file_wrong_fix | 488 | 52 | fastapi/_compat/v2.py, fastapi/dependencies/utils.py, reprod | fastapi/dependencies/utils.py | run_command=29 read_file=18 edit_file=3 write_file=2 | Agent exceeded session timeout (8.0 min) |
| rich_3772 | right_file_wrong_fix | 465 | 37 | rich/traceback.py | rich/traceback.py | read_file=20 run_command=14 write_file=1 edit_file=1 get_status=1 |  |
| rich_3518 | resolved | 224 | 28 | rich/table.py | rich/table.py | run_command=13 read_file=11 skill:locate.py=1 write_file=1 edit_file=1 |  |
| rich_3521 | agent_error | 483 | 30 |  | rich/segment.py | run_command=23 read_file=5 skill:locate.py=1 write_file=1 | Agent exceeded session timeout (8.0 min) |
| rich_3506 | agent_error | 483 | 30 |  | rich/segment.py | run_command=21 read_file=9 | Agent exceeded session timeout (8.0 min) |
| rich_2725 | resolved | 203 | 16 | rich/table.py | rich/table.py | run_command=10 edit_file=3 read_file=2 write_file=1 submit_patch=1 |  |
| rich_3043 | resolved | 485 | 27 | rich/_export_format.py | rich/_export_format.py | run_command=15 read_file=10 edit_file=1 skill:tests.py=1 get_status=1 |  |
| rich_3006 | resolved | 290 | 29 | rich/repr.py | rich/repr.py | run_command=22 read_file=3 write_file=2 edit_file=2 submit_patch=1 |  |

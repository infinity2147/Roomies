# Triage: c2_n30

resolved 8/30 (26.7%); mean time 415s; max 602s

Buckets: right_file_wrong_fix=10, resolved=8, agent_error=7, wrong_location=4, touched_tests_only=1

Tool usage: run_command=355, read_file=312, edit_file=100, write_file=45, skill:locate.py`,skill_name:=30, submit_patch=16, get_status=6, skill:locate.py=5, skill:tests.py=4, search_similar_code=1, get_code_neighbors=1, skill:check.py=1

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| fastapi_15661 | wrong_location | 490 | 32 | docs/en/docs/release-notes.md, fastapi/__init__.py, scripts/ | scripts/prepare_release.py | run_command=19 read_file=10 skill:locate.py=1 write_file=1 edit_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_15589 | touched_tests_only | 491 | 34 |  | fastapi/dependencies/utils.py | run_command=14 edit_file=10 read_file=6 write_file=4 | Agent exceeded session timeout (8.0 min) |
| requests_7309 | right_file_wrong_fix | 220 | 21 | src/requests/utils.py | src/requests/utils.py | run_command=11 read_file=6 edit_file=2 write_file=1 search_similar_code=1 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| rich_4077 | resolved | 486 | 33 | rich/file_proxy.py | rich/file_proxy.py | run_command=20 read_file=12 write_file=5 edit_file=1 |  |
| rich_4076 | wrong_location | 485 | 43 | rich/text.py | rich/ansi.py | run_command=21 read_file=16 edit_file=5 write_file=1 | Agent exceeded session timeout (8.0 min) |
| rich_4075 | wrong_location | 376 | 45 | repro.py | rich/console.py | read_file=28 run_command=13 write_file=5 get_status=1 edit_file=1 |  |
| fastapi_14258 | right_file_wrong_fix | 233 | 12 | fastapi/routing.py | fastapi/routing.py | run_command=5 read_file=5 skill:locate.py`,skill_name:=4 edit_file=3 write_file=1 |  |
| fastapi_14786 | resolved | 138 | 18 | fastapi/security/utils.py | fastapi/security/utils.py | run_command=8 skill:tests.py=3 read_file=2 write_file=2 edit_file=2 |  |
| fastapi_14492 | right_file_wrong_fix | 134 | 16 | docs_src/metadata/tutorial001_1_py39.py | docs_src/metadata/tutorial001_1_py39.py | run_command=10 read_file=4 edit_file=2 submit_patch=1 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| fastapi_14306 | right_file_wrong_fix | 488 | 45 | fastapi/dependencies/models.py, fastapi/exceptions.py | fastapi/exceptions.py, fastapi/routing.py | read_file=24 run_command=12 edit_file=9 submit_patch=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14448 | right_file_wrong_fix | 490 | 14 | fastapi/dependencies/models.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=6 read_file=5 edit_file=3 | Agent exceeded session timeout (8.0 min) |
| fastapi_14430 | agent_error | 484 | 15 |  | fastapi/_compat/v2.py | read_file=7 run_command=5 write_file=2 skill:locate.py=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14419 | agent_error | 485 | 20 |  | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=12 read_file=7 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14301 | resolved | 488 | 27 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=12 read_file=12 skill:locate.py`,skill_name:=7 write_file=2 edit_file=1 |  |
| fastapi_14246 | agent_error | 484 | 29 |  | fastapi/_compat/v2.py | read_file=15 run_command=13 skill:locate.py`,skill_name:=7 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_13713 | agent_error | 484 | 19 |  | fastapi/applications.py, fastapi/openapi/utils.py | edit_file=19 read_file=13 run_command=6 | Agent exceeded session timeout (8.0 min) |
| httpx_3672 | agent_error | 481 | 24 |  | src/ahttpx/_parsers.py, src/ahttpx/_pool.py, src/ahttpx/_ser | read_file=14 run_command=10 skill:locate.py`,skill_name:=7 | Agent exceeded session timeout (8.0 min) |
| fastapi_15800 | right_file_wrong_fix | 470 | 32 | fastapi/applications.py, fastapi/routing.py | fastapi/applications.py, fastapi/routing.py | read_file=15 run_command=12 edit_file=4 write_file=1 submit_patch=1 |  |
| fastapi_14371 | right_file_wrong_fix | 421 | 20 | fastapi/param_functions.py, fastapi/params.py | fastapi/_compat/v2.py, fastapi/dependencies/utils.py, fastap | run_command=9 read_file=6 edit_file=3 write_file=2 submit_patch=1 |  |
| fastapi_14605 | resolved | 250 | 40 | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | read_file=17 edit_file=15 run_command=8 submit_patch=1 |  |
| fastapi_13537 | resolved | 488 | 18 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | read_file=8 run_command=7 skill:locate.py=1 edit_file=1 write_file=1 |  |
| fastapi_14953 | right_file_wrong_fix | 491 | 42 | fastapi/_compat/v2.py, fastapi/datastructures.py | fastapi/_compat/v2.py, fastapi/datastructures.py | run_command=22 read_file=15 edit_file=3 write_file=2 submit_patch=1 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| fastapi_14616 | wrong_location | 489 | 38 | repro_debug.py, repro_debug_2.py, repro_issue.py | fastapi/dependencies/utils.py | run_command=22 read_file=10 write_file=6 | Agent exceeded session timeout (8.0 min) |
| rich_3772 | right_file_wrong_fix | 602 | 31 | repro.py, repro_recursion.py, rich/traceback.py | rich/traceback.py | read_file=14 run_command=10 write_file=4 edit_file=3 submit_patch=2 |  |
| rich_3518 | resolved | 245 | 27 | rich/table.py | rich/table.py | read_file=13 run_command=12 skill:locate.py`,skill_name:=5 edit_file=4 write_file=1 |  |
| rich_3521 | agent_error | 482 | 12 |  | rich/segment.py | run_command=8 read_file=3 skill:locate.py=1 | Agent exceeded session timeout (8.0 min) |
| rich_3506 | agent_error | 482 | 12 |  | rich/segment.py | read_file=6 run_command=4 skill:locate.py=1 skill:tests.py=1 | Agent exceeded session timeout (8.0 min) |
| rich_2725 | resolved | 485 | 28 | rich/table.py | rich/table.py | run_command=17 read_file=9 edit_file=1 write_file=1 get_status=1 |  |
| rich_3043 | right_file_wrong_fix | 365 | 21 | rich/_export_format.py | rich/_export_format.py | run_command=11 read_file=6 edit_file=3 skill:check.py=1 get_status=1 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| rich_3006 | resolved | 244 | 25 | rich/repr.py | rich/repr.py | run_command=16 read_file=4 edit_file=4 submit_patch=2 write_file=1 |  |

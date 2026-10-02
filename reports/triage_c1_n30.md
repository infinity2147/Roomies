# Triage: c1_n30

resolved 8/30 (26.7%); mean time 415s; max 603s

Buckets: right_file_wrong_fix=10, resolved=8, agent_error=6, wrong_location=5, no_patch=1

Tool usage: run_command=323, read_file=279, edit_file=129, write_file=60, skill:locate.py=46, skill:show.py=20, skill:tests.py=14, submit_patch=13, search_similar_code=4, skill:?=3, skill:show.py`=1, load_skill=1, skill:show.py」=1, get_code_neighbors=1, skill:tests.py`,skill_name:=1

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| fastapi_15661 | wrong_location | 489 | 25 | scripts/release.py | scripts/prepare_release.py | run_command=10 read_file=9 search_similar_code=4 write_file=1 edit_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_15589 | resolved | 489 | 17 | fastapi/dependencies/utils.py, repro.py | fastapi/dependencies/utils.py | run_command=6 read_file=5 edit_file=4 write_file=2 |  |
| requests_7309 | right_file_wrong_fix | 199 | 18 | src/requests/utils.py | src/requests/utils.py | read_file=6 run_command=6 skill:locate.py=2 edit_file=2 write_file=1 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| rich_4077 | wrong_location | 485 | 33 | repro_isatty.py, rich/console.py | rich/file_proxy.py | read_file=16 run_command=13 write_file=3 edit_file=1 | Agent exceeded session timeout (8.0 min) |
| rich_4076 | no_patch | 464 | 45 |  | rich/ansi.py | run_command=19 read_file=18 skill:show.py=5 skill:locate.py=2 edit_file=2 |  |
| rich_4075 | agent_error | 488 | 26 |  | rich/console.py | run_command=10 skill:show.py=10 skill:locate.py=4 read_file=2 load_skill=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14258 | right_file_wrong_fix | 488 | 43 | fastapi/routing.py, repro.py | fastapi/routing.py | read_file=20 run_command=13 write_file=5 edit_file=3 skill:locate.py=2 | Agent exceeded session timeout (8.0 min) |
| fastapi_14786 | resolved | 123 | 15 | fastapi/security/utils.py | fastapi/security/utils.py | run_command=7 write_file=3 skill:locate.py=2 read_file=1 edit_file=1 |  |
| fastapi_14492 | right_file_wrong_fix | 99 | 13 | docs_src/metadata/tutorial001_1_py39.py | docs_src/metadata/tutorial001_1_py39.py | run_command=8 read_file=3 edit_file=2 submit_patch=1 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| fastapi_14306 | agent_error | 485 | 37 |  | fastapi/exceptions.py, fastapi/routing.py | read_file=22 run_command=11 skill:locate.py=4 | Agent exceeded session timeout (8.0 min) |
| fastapi_14448 | agent_error | 484 | 13 |  | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=9 read_file=2 write_file=1 edit_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14430 | wrong_location | 489 | 13 | repro_bug.py | fastapi/_compat/v2.py | read_file=4 run_command=4 write_file=3 skill:locate.py=2 | Agent exceeded session timeout (8.0 min) |
| fastapi_14419 | resolved | 408 | 25 | fastapi/dependencies/models.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=12 read_file=5 skill:locate.py=4 edit_file=2 write_file=2 |  |
| fastapi_14301 | resolved | 487 | 34 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | read_file=16 run_command=14 skill:locate.py=2 edit_file=1 write_file=1 |  |
| fastapi_14246 | agent_error | 484 | 41 |  | fastapi/_compat/v2.py | read_file=20 run_command=19 write_file=6 skill:locate.py=2 | Agent exceeded session timeout (8.0 min) |
| fastapi_13713 | right_file_wrong_fix | 267 | 29 | fastapi/applications.py, fastapi/openapi/utils.py | fastapi/applications.py, fastapi/openapi/utils.py | read_file=8 run_command=6 edit_file=6 skill:locate.py=4 skill:show.py=3 |  |
| httpx_3672 | right_file_wrong_fix | 483 | 29 | src/ahttpx/_parsers.py, src/httpx/_network.py, src/httpx/_pa | src/ahttpx/_parsers.py, src/ahttpx/_pool.py, src/ahttpx/_ser | read_file=15 edit_file=8 run_command=6 | Agent exceeded session timeout (8.0 min) |
| fastapi_15800 | right_file_wrong_fix | 490 | 38 | fastapi/applications.py, fastapi/routing.py | fastapi/applications.py, fastapi/routing.py | run_command=16 read_file=10 edit_file=7 write_file=4 skill:?=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14371 | right_file_wrong_fix | 492 | 43 | fastapi/_compat/v2.py, repro_alias.py | fastapi/_compat/v2.py, fastapi/dependencies/utils.py, fastap | read_file=17 run_command=16 write_file=4 edit_file=4 skill:show.py=2 | Agent exceeded session timeout (8.0 min) |
| fastapi_14605 | right_file_wrong_fix | 464 | 33 | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | edit_file=60 read_file=16 run_command=4 | Agent exceeded turns budget (80 turns) |
| fastapi_13537 | resolved | 308 | 18 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=6 skill:tests.py=5 read_file=3 skill:locate.py=2 write_file=1 |  |
| fastapi_14953 | right_file_wrong_fix | 507 | 32 | fastapi/_compat/v2.py, fastapi/datastructures.py | fastapi/_compat/v2.py, fastapi/datastructures.py | run_command=19 read_file=7 write_file=3 edit_file=2 skill:tests.py`,skill_name:=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14616 | wrong_location | 488 | 38 | fastapi/_compat/v2.py, repro.py, repro_fix.py | fastapi/dependencies/utils.py | run_command=14 read_file=12 write_file=7 skill:locate.py=3 edit_file=2 | Agent exceeded session timeout (8.0 min) |
| rich_3772 | wrong_location | 603 | 19 | repro_recursion.py, repro_recursion_cause.py, repro_recursio | rich/traceback.py | run_command=8 read_file=7 write_file=4 | Agent exceeded session timeout (8.0 min) |
| rich_3518 | resolved | 261 | 28 | rich/table.py | rich/table.py | run_command=14 read_file=9 edit_file=8 skill:locate.py=2 write_file=2 |  |
| rich_3521 | agent_error | 482 | 14 |  | rich/segment.py | run_command=6 read_file=5 skill:locate.py=3 | Agent exceeded session timeout (8.0 min) |
| rich_3506 | agent_error | 482 | 16 |  | rich/segment.py | run_command=10 read_file=4 skill:?=1 skill:locate.py=1 write_file=1 | Agent exceeded session timeout (8.0 min) |
| rich_2725 | resolved | 236 | 13 | rich/table.py | rich/table.py | run_command=6 read_file=3 skill:locate.py=2 write_file=1 edit_file=1 |  |
| rich_3043 | right_file_wrong_fix | 483 | 26 | rich/_export_format.py | rich/_export_format.py | run_command=12 read_file=7 edit_file=5 skill:locate.py=2 skill:tests.py=2 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| rich_3006 | resolved | 255 | 33 | rich/repr.py | rich/repr.py | run_command=19 read_file=7 edit_file=5 write_file=3 skill:tests.py=2 |  |

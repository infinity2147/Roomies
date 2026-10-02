# Triage: c3_n30

resolved 10/30 (33.3%); mean time 428s; max 607s

Buckets: right_file_wrong_fix=11, resolved=10, agent_error=5, wrong_location=3, no_patch=1

Tool usage: run_command=373, read_file=334, edit_file=179, write_file=37, submit_patch=16, skill:locate.py=4, skill:tests.py=3, get_status=2, skill:check.py=1

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| fastapi_15661 | right_file_wrong_fix | 491 | 27 | scripts/prepare_release.py | scripts/prepare_release.py | run_command=16 read_file=9 write_file=2 | Agent exceeded session timeout (8.0 min) |
| fastapi_15589 | wrong_location | 491 | 27 | reproduce_issue.py | fastapi/dependencies/utils.py | read_file=16 run_command=9 write_file=2 | Agent exceeded session timeout (8.0 min) |
| requests_7309 | right_file_wrong_fix | 265 | 19 | src/requests/utils.py | src/requests/utils.py | run_command=9 read_file=6 edit_file=3 skill:tests.py=1 submit_patch=1 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| rich_4077 | wrong_location | 304 | 27 | rich/console.py | rich/file_proxy.py | run_command=13 read_file=12 edit_file=1 write_file=1 submit_patch=1 |  |
| rich_4076 | no_patch | 471 | 45 |  | rich/ansi.py | read_file=25 run_command=21 submit_patch=1 |  |
| rich_4075 | resolved | 460 | 45 | rich/console.py | rich/console.py | run_command=27 read_file=17 edit_file=9 write_file=1 get_status=1 |  |
| fastapi_14258 | right_file_wrong_fix | 439 | 45 | fastapi/routing.py | fastapi/routing.py | read_file=27 run_command=16 edit_file=6 write_file=1 submit_patch=1 |  |
| fastapi_14786 | resolved | 121 | 11 | fastapi/security/utils.py | fastapi/security/utils.py | run_command=5 edit_file=3 read_file=2 write_file=1 submit_patch=1 |  |
| fastapi_14492 | resolved | 154 | 17 | docs_src/metadata/tutorial001_1_py39.py | docs_src/metadata/tutorial001_1_py39.py | run_command=12 read_file=4 edit_file=1 submit_patch=1 |  |
| fastapi_14306 | right_file_wrong_fix | 490 | 44 | fastapi/exceptions.py, fastapi/routing.py | fastapi/exceptions.py, fastapi/routing.py | read_file=17 run_command=14 edit_file=13 | Agent exceeded session timeout (8.0 min) |
| fastapi_14448 | right_file_wrong_fix | 607 | 10 | fastapi/dependencies/models.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | read_file=4 run_command=3 skill:locate.py=1 edit_file=1 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14430 | agent_error | 485 | 12 |  | fastapi/_compat/v2.py | run_command=7 read_file=4 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14419 | resolved | 489 | 19 | fastapi/dependencies/models.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | read_file=11 run_command=6 edit_file=1 write_file=1 |  |
| fastapi_14301 | resolved | 380 | 23 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=12 read_file=7 edit_file=3 write_file=1 submit_patch=1 |  |
| fastapi_14246 | agent_error | 487 | 42 |  | fastapi/_compat/v2.py | run_command=24 read_file=17 skill:locate.py=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_13713 | right_file_wrong_fix | 489 | 17 | fastapi/applications.py | fastapi/applications.py, fastapi/openapi/utils.py | edit_file=24 read_file=11 run_command=5 | Agent exceeded session timeout (8.0 min) |
| httpx_3672 | right_file_wrong_fix | 484 | 19 | src/httpx/_parsers.py, src/httpx/_server.py, src/httpx/_stre | src/ahttpx/_parsers.py, src/ahttpx/_pool.py, src/ahttpx/_ser | edit_file=36 read_file=12 run_command=3 | Agent exceeded session timeout (8.0 min) |
| fastapi_15800 | right_file_wrong_fix | 492 | 44 | fastapi/applications.py, fastapi/routing.py | fastapi/applications.py, fastapi/routing.py | read_file=26 run_command=14 edit_file=4 | Agent exceeded session timeout (8.0 min) |
| fastapi_14371 | agent_error | 485 | 30 |  | fastapi/_compat/v2.py, fastapi/dependencies/utils.py, fastap | run_command=18 read_file=11 skill:tests.py=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14605 | resolved | 490 | 45 | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | edit_file=38 read_file=18 run_command=17 submit_patch=1 |  |
| fastapi_13537 | resolved | 272 | 13 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=7 read_file=3 skill:locate.py=1 write_file=1 edit_file=1 |  |
| fastapi_14953 | right_file_wrong_fix | 448 | 40 | fastapi/_compat/v2.py, fastapi/datastructures.py | fastapi/_compat/v2.py, fastapi/datastructures.py | run_command=20 read_file=11 write_file=6 edit_file=3 submit_patch=2 |  |
| fastapi_14616 | wrong_location | 489 | 36 | check_metadata.py, fastapi/_compat/v2.py, reproduce_issue.py | fastapi/dependencies/utils.py | run_command=19 read_file=9 write_file=4 edit_file=4 | Agent exceeded session timeout (8.0 min) |
| rich_3772 | right_file_wrong_fix | 604 | 32 | rich/traceback.py | rich/traceback.py | read_file=15 run_command=8 write_file=6 edit_file=3 | Agent exceeded session timeout (8.0 min) |
| rich_3518 | resolved | 219 | 13 | rich/table.py | rich/table.py | read_file=7 edit_file=7 run_command=3 skill:locate.py=1 write_file=1 |  |
| rich_3521 | agent_error | 485 | 16 |  | rich/segment.py | run_command=9 read_file=6 skill:tests.py=1 | Agent exceeded session timeout (8.0 min) |
| rich_3506 | agent_error | 484 | 13 |  | rich/segment.py | run_command=6 read_file=6 skill:check.py=1 | Agent exceeded session timeout (8.0 min) |
| rich_2725 | right_file_wrong_fix | 468 | 20 | rich/table.py | rich/table.py | run_command=12 read_file=5 edit_file=2 write_file=1 submit_patch=1 |  |
| rich_3043 | resolved | 396 | 22 | rich/_export_format.py | rich/_export_format.py | run_command=10 read_file=8 edit_file=6 write_file=5 submit_patch=1 |  |
| rich_3006 | resolved | 396 | 41 | rich/repr.py | rich/repr.py | run_command=28 edit_file=10 read_file=8 write_file=1 submit_patch=1 |  |

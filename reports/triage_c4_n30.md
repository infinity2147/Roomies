# Triage: c4_n30

resolved 9/30 (30.0%); mean time 409s; max 493s

Buckets: agent_error=10, resolved=9, right_file_wrong_fix=8, wrong_location=3

Tool usage: run_command=382, read_file=294, edit_file=88, write_file=43, submit_patch=13, skill:tests.py=6, get_status=4, skill:locate.py=2, search_similar_code=1, skill:check.py=1

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| fastapi_15661 | wrong_location | 422 | 24 | scripts/release.py | scripts/prepare_release.py | run_command=13 read_file=8 write_file=2 search_similar_code=1 get_status=1 |  |
| fastapi_15589 | wrong_location | 491 | 33 | repro.py, repro_model.py | fastapi/dependencies/utils.py | run_command=15 read_file=13 write_file=5 | Agent exceeded session timeout (8.0 min) |
| requests_7309 | right_file_wrong_fix | 238 | 16 | src/requests/utils.py | src/requests/utils.py | run_command=8 read_file=3 write_file=3 edit_file=2 submit_patch=1 |  |
| rich_4077 | agent_error | 483 | 15 |  | rich/file_proxy.py | run_command=10 read_file=5 | Agent exceeded session timeout (8.0 min) |
| rich_4076 | agent_error | 482 | 20 |  | rich/ansi.py | run_command=14 read_file=4 skill:locate.py=1 write_file=1 | Agent exceeded session timeout (8.0 min) |
| rich_4075 | agent_error | 483 | 31 |  | rich/console.py | run_command=17 read_file=13 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14258 | right_file_wrong_fix | 489 | 45 | fastapi/routing.py, repro.py | fastapi/routing.py | run_command=23 read_file=18 write_file=3 edit_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14786 | resolved | 229 | 12 | fastapi/security/utils.py | fastapi/security/utils.py | run_command=8 read_file=1 write_file=1 edit_file=1 skill:tests.py=1 |  |
| fastapi_14492 | resolved | 186 | 19 | docs_src/metadata/tutorial001_1_py39.py | docs_src/metadata/tutorial001_1_py39.py | run_command=13 read_file=5 edit_file=1 get_status=1 submit_patch=1 |  |
| fastapi_14306 | right_file_wrong_fix | 413 | 45 | fastapi/dependencies/models.py, fastapi/exceptions.py, fasta | fastapi/exceptions.py, fastapi/routing.py | read_file=21 run_command=18 edit_file=6 submit_patch=1 |  |
| fastapi_14448 | right_file_wrong_fix | 491 | 14 | fastapi/dependencies/models.py, fastapi/utils.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | read_file=6 run_command=5 edit_file=3 | Agent exceeded session timeout (8.0 min) |
| fastapi_14430 | agent_error | 485 | 13 |  | fastapi/_compat/v2.py | run_command=7 read_file=4 write_file=1 skill:locate.py=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14419 | right_file_wrong_fix | 385 | 19 | fastapi/dependencies/models.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=10 read_file=7 write_file=1 edit_file=1 submit_patch=1 |  |
| fastapi_14301 | resolved | 202 | 15 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=6 read_file=5 skill:tests.py=2 edit_file=1 write_file=1 |  |
| fastapi_14246 | wrong_location | 493 | 28 | repro.py, repro_list.py | fastapi/_compat/v2.py | run_command=12 read_file=11 write_file=5 | Agent exceeded session timeout (8.0 min) |
| fastapi_13713 | agent_error | 485 | 14 |  | fastapi/applications.py, fastapi/openapi/utils.py | read_file=10 edit_file=7 run_command=4 | Agent exceeded session timeout (8.0 min) |
| httpx_3672 | right_file_wrong_fix | 483 | 28 | src/httpx/_network.py, src/httpx/_parsers.py, src/httpx/_ser | src/ahttpx/_parsers.py, src/ahttpx/_pool.py, src/ahttpx/_ser | read_file=15 edit_file=7 run_command=5 skill:tests.py=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_15800 | agent_error | 487 | 43 |  | fastapi/applications.py, fastapi/routing.py | read_file=26 run_command=17 | Agent exceeded session timeout (8.0 min) |
| fastapi_14371 | agent_error | 485 | 36 |  | fastapi/_compat/v2.py, fastapi/dependencies/utils.py, fastap | run_command=19 read_file=13 edit_file=2 skill:tests.py=1 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14605 | right_file_wrong_fix | 490 | 38 | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | edit_file=25 read_file=20 run_command=7 | Agent exceeded session timeout (8.0 min) |
| fastapi_13537 | resolved | 284 | 12 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=7 read_file=3 write_file=2 edit_file=1 submit_patch=1 |  |
| fastapi_14953 | right_file_wrong_fix | 491 | 36 | fastapi/_compat/v2.py, fastapi/datastructures.py | fastapi/_compat/v2.py, fastapi/datastructures.py | run_command=18 read_file=15 edit_file=3 | Agent exceeded session timeout (8.0 min) |
| fastapi_14616 | resolved | 493 | 43 | fastapi/_compat/v2.py, repro.py | fastapi/dependencies/utils.py | run_command=16 read_file=14 write_file=9 edit_file=5 |  |
| rich_3772 | agent_error | 483 | 45 |  | rich/traceback.py | run_command=36 read_file=8 write_file=1 | Agent exceeded session timeout (8.0 min) |
| rich_3518 | resolved | 306 | 29 | rich/table.py | rich/table.py | run_command=16 read_file=11 edit_file=11 write_file=2 submit_patch=1 |  |
| rich_3521 | agent_error | 483 | 23 |  | rich/segment.py | run_command=11 read_file=11 write_file=1 | Agent exceeded session timeout (8.0 min) |
| rich_3506 | agent_error | 483 | 13 |  | rich/segment.py | read_file=7 run_command=6 | Agent exceeded session timeout (8.0 min) |
| rich_2725 | resolved | 198 | 16 | rich/table.py | rich/table.py | run_command=7 read_file=4 edit_file=3 write_file=2 get_status=1 |  |
| rich_3043 | resolved | 438 | 31 | rich/_export_format.py | rich/_export_format.py | run_command=16 read_file=9 edit_file=4 skill:tests.py=1 skill:check.py=1 |  |
| rich_3006 | resolved | 198 | 26 | rich/repr.py | rich/repr.py | run_command=18 read_file=4 edit_file=4 submit_patch=2 write_file=1 |  |

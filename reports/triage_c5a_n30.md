# Triage: c5a_n30

resolved 9/30 (30.0%); mean time 401s; max 593s

Buckets: right_file_wrong_fix=11, resolved=9, agent_error=6, wrong_location=3, no_patch=1

Tool usage: run_command=389, read_file=296, edit_file=109, write_file=38, submit_patch=20, get_status=7, skill:check.py=4, skill:tests.py=4, search_similar_code=2, get_code_neighbors=2, skill:show.py=1

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| fastapi_15661 | wrong_location | 392 | 22 | scripts/release.py | scripts/prepare_release.py | run_command=13 read_file=6 write_file=2 submit_patch=2 search_similar_code=1 |  |
| fastapi_15589 | right_file_wrong_fix | 497 | 22 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | read_file=11 run_command=10 edit_file=1 | Agent exceeded session timeout (8.0 min) |
| requests_7309 | right_file_wrong_fix | 376 | 32 | src/requests/utils.py | src/requests/utils.py | run_command=19 read_file=8 write_file=2 edit_file=2 skill:check.py=1 |  |
| rich_4077 | agent_error | 484 | 24 |  | rich/file_proxy.py | run_command=14 read_file=9 write_file=1 | Agent exceeded session timeout (8.0 min) |
| rich_4076 | agent_error | 487 | 45 |  | rich/ansi.py | read_file=23 run_command=22 | Agent exceeded session timeout (8.0 min) |
| rich_4075 | no_patch | 416 | 45 |  | rich/console.py | read_file=27 run_command=19 edit_file=2 submit_patch=2 write_file=1 |  |
| fastapi_14258 | right_file_wrong_fix | 492 | 35 | fastapi/routing.py, repro.py | fastapi/routing.py | read_file=17 run_command=13 edit_file=4 write_file=3 | Agent exceeded session timeout (8.0 min) |
| fastapi_14786 | resolved | 231 | 12 | fastapi/security/utils.py | fastapi/security/utils.py | run_command=5 read_file=2 write_file=1 edit_file=1 get_code_neighbors=1 |  |
| fastapi_14492 | resolved | 84 | 9 | docs_src/metadata/tutorial001_1_py39.py | docs_src/metadata/tutorial001_1_py39.py | run_command=6 read_file=2 edit_file=1 get_status=1 submit_patch=1 |  |
| fastapi_14306 | agent_error | 492 | 45 |  | fastapi/exceptions.py, fastapi/routing.py | read_file=25 run_command=21 get_status=1 edit_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14448 | right_file_wrong_fix | 495 | 9 | fastapi/dependencies/models.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=7 read_file=1 edit_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14430 | wrong_location | 593 | 26 | repro.py | fastapi/_compat/v2.py | run_command=21 read_file=4 write_file=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_14419 | resolved | 444 | 23 | fastapi/dependencies/models.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=13 read_file=7 edit_file=2 submit_patch=2 write_file=1 |  |
| fastapi_14301 | resolved | 492 | 22 | fastapi/dependencies/utils.py, repro.py | fastapi/dependencies/utils.py | run_command=11 read_file=7 write_file=5 edit_file=2 skill:show.py=1 |  |
| fastapi_14246 | wrong_location | 491 | 41 | repro.py | fastapi/_compat/v2.py | run_command=18 read_file=11 edit_file=9 write_file=3 | Agent exceeded session timeout (8.0 min) |
| fastapi_13713 | agent_error | 486 | 14 |  | fastapi/applications.py, fastapi/openapi/utils.py | edit_file=17 read_file=10 run_command=4 | Agent exceeded session timeout (8.0 min) |
| httpx_3672 | right_file_wrong_fix | 483 | 32 | src/httpx/_network.py, src/httpx/_parsers.py, src/httpx/_ser | src/ahttpx/_parsers.py, src/ahttpx/_pool.py, src/ahttpx/_ser | read_file=19 edit_file=7 run_command=4 skill:tests.py=1 skill:check.py=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_15800 | right_file_wrong_fix | 328 | 33 | fastapi/applications.py, fastapi/routing.py | fastapi/applications.py, fastapi/routing.py | run_command=16 read_file=11 edit_file=4 get_code_neighbors=1 write_file=1 |  |
| fastapi_14371 | right_file_wrong_fix | 365 | 21 | fastapi/_compat/v2.py | fastapi/_compat/v2.py, fastapi/dependencies/utils.py, fastap | run_command=10 read_file=8 search_similar_code=1 edit_file=1 write_file=1 |  |
| fastapi_14605 | right_file_wrong_fix | 493 | 45 | fastapi/__init__.py, fastapi/dependencies/utils.py, fastapi/ | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | edit_file=34 read_file=19 run_command=17 submit_patch=1 | Agent exceeded session timeout (8.0 min) |
| fastapi_13537 | resolved | 302 | 16 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=8 read_file=4 edit_file=1 write_file=1 skill:tests.py=1 |  |
| fastapi_14953 | right_file_wrong_fix | 224 | 19 | fastapi/datastructures.py | fastapi/_compat/v2.py, fastapi/datastructures.py | run_command=10 read_file=7 edit_file=2 write_file=1 get_status=1 |  |
| fastapi_14616 | right_file_wrong_fix | 490 | 44 | fastapi/dependencies/utils.py, repro.py | fastapi/dependencies/utils.py | run_command=21 read_file=13 write_file=8 edit_file=2 | Agent exceeded session timeout (8.0 min) |
| rich_3772 | right_file_wrong_fix | 543 | 27 | rich/traceback.py | rich/traceback.py | read_file=13 run_command=8 edit_file=4 write_file=2 get_status=1 |  |
| rich_3518 | resolved | 186 | 20 | rich/table.py | rich/table.py | run_command=11 read_file=7 edit_file=4 write_file=1 submit_patch=1 |  |
| rich_3521 | agent_error | 483 | 22 |  | rich/segment.py | run_command=17 read_file=5 | Agent exceeded session timeout (8.0 min) |
| rich_3506 | agent_error | 483 | 17 |  | rich/segment.py | run_command=12 read_file=5 | Agent exceeded session timeout (8.0 min) |
| rich_2725 | resolved | 262 | 14 | rich/table.py | rich/table.py | run_command=9 read_file=3 write_file=1 edit_file=1 get_status=1 |  |
| rich_3043 | resolved | 251 | 26 | rich/_export_format.py | rich/_export_format.py | run_command=15 read_file=8 submit_patch=2 edit_file=1 skill:tests.py=1 |  |
| rich_3006 | resolved | 196 | 24 | rich/repr.py | rich/repr.py | run_command=15 edit_file=5 read_file=4 write_file=1 submit_patch=1 |  |

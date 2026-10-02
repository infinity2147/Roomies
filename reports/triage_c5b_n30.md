# Triage: c5b_n30

resolved 7/30 (23.3%); mean time 186s; max 488s

Buckets: no_patch=13, resolved=7, right_file_wrong_fix=6, wrong_location=2, agent_error=1, touched_tests_only=1

Tool usage: run_command=691, read_file=244, edit_file=140, submit_patch=27, write_file=16, get_status=7, skill:locate.py=3, skill:check.py=1

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| fastapi_15661 | no_patch | 107 | 38 |  | scripts/prepare_release.py | run_command=35 read_file=3 submit_patch=1 |  |
| fastapi_15589 | agent_error | 485 | 26 |  | fastapi/dependencies/utils.py | run_command=19 read_file=7 | Agent exceeded session timeout (8.0 min) |
| requests_7309 | right_file_wrong_fix | 200 | 43 | repro.py, src/requests/utils.py | src/requests/utils.py | run_command=33 read_file=7 write_file=2 edit_file=1 submit_patch=1 |  |
| rich_4077 | resolved | 116 | 40 | rich/file_proxy.py | rich/file_proxy.py | read_file=21 run_command=18 edit_file=1 submit_patch=1 |  |
| rich_4076 | no_patch | 104 | 44 |  | rich/ansi.py | run_command=44 submit_patch=1 |  |
| rich_4075 | no_patch | 167 | 44 |  | rich/console.py | run_command=42 skill:locate.py=1 read_file=1 submit_patch=1 |  |
| fastapi_14258 | right_file_wrong_fix | 66 | 8 | fastapi/routing.py | fastapi/routing.py | run_command=4 read_file=3 edit_file=2 get_status=1 submit_patch=1 |  |
| fastapi_14786 | resolved | 60 | 8 | fastapi/security/utils.py | fastapi/security/utils.py | run_command=4 write_file=2 read_file=1 edit_file=1 get_status=1 |  |
| fastapi_14492 | resolved | 56 | 10 | docs_src/metadata/tutorial001_1_py39.py | docs_src/metadata/tutorial001_1_py39.py | run_command=7 edit_file=4 read_file=2 get_status=1 submit_patch=1 |  |
| fastapi_14306 | no_patch | 97 | 39 |  | fastapi/exceptions.py, fastapi/routing.py | run_command=29 read_file=10 submit_patch=1 |  |
| fastapi_14448 | no_patch | 112 | 43 |  | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=39 read_file=4 submit_patch=1 |  |
| fastapi_14430 | no_patch | 394 | 36 |  | fastapi/_compat/v2.py | run_command=30 read_file=6 submit_patch=1 |  |
| fastapi_14419 | no_patch | 111 | 39 |  | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=27 read_file=11 skill:locate.py=1 get_status=1 submit_patch=1 |  |
| fastapi_14301 | resolved | 79 | 16 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=10 write_file=3 read_file=2 edit_file=1 get_status=1 |  |
| fastapi_14246 | no_patch | 95 | 44 |  | fastapi/_compat/v2.py | run_command=43 skill:locate.py=1 submit_patch=1 |  |
| fastapi_13713 | touched_tests_only | 188 | 45 |  | fastapi/applications.py, fastapi/openapi/utils.py | read_file=34 run_command=9 write_file=2 edit_file=1 submit_patch=1 |  |
| httpx_3672 | right_file_wrong_fix | 251 | 24 | src/httpx/_parsers.py, src/httpx/_server.py | src/ahttpx/_parsers.py, src/ahttpx/_pool.py, src/ahttpx/_ser | read_file=9 edit_file=9 run_command=6 submit_patch=1 |  |
| fastapi_15800 | no_patch | 114 | 42 |  | fastapi/applications.py, fastapi/routing.py | run_command=35 read_file=7 submit_patch=1 |  |
| fastapi_14371 | no_patch | 189 | 42 |  | fastapi/_compat/v2.py, fastapi/dependencies/utils.py, fastap | run_command=39 read_file=3 submit_patch=1 |  |
| fastapi_14605 | right_file_wrong_fix | 302 | 28 | fastapi/dependencies/utils.py, fastapi/exceptions.py | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | edit_file=60 read_file=12 run_command=8 | Agent exceeded turns budget (80 turns) |
| fastapi_13537 | wrong_location | 488 | 8 | repro.py | fastapi/dependencies/utils.py | edit_file=11 run_command=3 read_file=3 write_file=2 | Agent exceeded session timeout (8.0 min) |
| fastapi_14953 | right_file_wrong_fix | 136 | 43 | fastapi/datastructures.py | fastapi/_compat/v2.py, fastapi/datastructures.py | run_command=41 read_file=1 edit_file=1 submit_patch=1 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| fastapi_14616 | wrong_location | 210 | 45 | fastapi/_compat/shared.py | fastapi/dependencies/utils.py | run_command=40 edit_file=5 read_file=4 submit_patch=1 |  |
| rich_3772 | no_patch | 299 | 43 |  | rich/traceback.py | run_command=37 read_file=6 submit_patch=1 |  |
| rich_3518 | resolved | 138 | 23 | rich/table.py | rich/table.py | read_file=14 edit_file=11 run_command=5 write_file=2 skill:check.py=1 |  |
| rich_3521 | no_patch | 378 | 43 |  | rich/segment.py | read_file=28 run_command=15 submit_patch=1 |  |
| rich_3506 | no_patch | 142 | 44 |  | rich/segment.py | run_command=40 read_file=4 submit_patch=1 |  |
| rich_2725 | resolved | 185 | 42 | rich/table.py | rich/table.py | read_file=33 edit_file=6 run_command=3 get_status=1 submit_patch=1 |  |
| rich_3043 | right_file_wrong_fix | 213 | 40 | rich/_export_format.py | rich/_export_format.py | edit_file=25 run_command=8 read_file=7 submit_patch=1 |  |
| rich_3006 | resolved | 85 | 23 | reproduce_issue.py, reproduce_issue_v2.py, rich/repr.py | rich/repr.py | run_command=18 write_file=3 read_file=1 edit_file=1 get_status=1 |  |

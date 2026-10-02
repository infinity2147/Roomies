# Triage: c6a_n30

resolved 9/30 (30.0%); mean time 270s; max 489s

Buckets: resolved=9, no_patch=7, right_file_wrong_fix=6, agent_error=4, wrong_location=3, touched_tests_only=1

Tool usage: run_command=1307, read_file=337, edit_file=222, submit_patch=26, write_file=17, get_status=10, skill:locate.py=6

| task | bucket | sec | tools | patched src | gold | usage | error |
|---|---|---|---|---|---|---|---|
| fastapi_15661 | no_patch | 240 | 93 |  | scripts/prepare_release.py | run_command=89 read_file=4 submit_patch=1 |  |
| fastapi_15589 | touched_tests_only | 331 | 64 |  | fastapi/dependencies/utils.py | run_command=38 read_file=21 write_file=5 get_status=1 submit_patch=1 |  |
| requests_7309 | right_file_wrong_fix | 238 | 39 | repro.py, src/requests/utils.py | src/requests/utils.py | run_command=20 edit_file=9 read_file=8 write_file=2 submit_patch=1 | Failed to apply test_patch: git apply /tmp/swegemma_sandbox_ |
| rich_4077 | resolved | 81 | 20 | rich/file_proxy.py | rich/file_proxy.py | read_file=10 run_command=9 edit_file=1 get_status=1 submit_patch=1 |  |
| rich_4076 | no_patch | 229 | 91 |  | rich/ansi.py | run_command=86 read_file=3 skill:locate.py=2 submit_patch=1 |  |
| rich_4075 | wrong_location | 355 | 94 | pyproject.toml, rich/text.py | rich/console.py | run_command=86 edit_file=4 read_file=3 skill:locate.py=1 submit_patch=1 |  |
| fastapi_14258 | agent_error | 489 | 11 |  | fastapi/routing.py | edit_file=96 read_file=7 run_command=4 | Agent exceeded session timeout (8.0 min) |
| fastapi_14786 | resolved | 62 | 8 | fastapi/security/utils.py | fastapi/security/utils.py | run_command=4 write_file=2 read_file=1 edit_file=1 get_status=1 |  |
| fastapi_14492 | resolved | 56 | 19 | docs_src/metadata/tutorial001_1_py39.py | docs_src/metadata/tutorial001_1_py39.py | run_command=15 read_file=3 edit_file=1 get_status=1 submit_patch=1 |  |
| fastapi_14306 | right_file_wrong_fix | 244 | 91 | fastapi/exceptions.py | fastapi/exceptions.py, fastapi/routing.py | run_command=50 read_file=39 edit_file=3 submit_patch=1 |  |
| fastapi_14448 | wrong_location | 287 | 93 | fastapi/routing.py | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | run_command=82 read_file=6 write_file=4 edit_file=1 submit_patch=1 |  |
| fastapi_14430 | no_patch | 331 | 98 |  | fastapi/_compat/v2.py | run_command=91 read_file=7 submit_patch=1 |  |
| fastapi_14419 | agent_error | 485 | 62 |  | fastapi/dependencies/models.py, fastapi/dependencies/utils.p | read_file=34 run_command=28 | Agent exceeded session timeout (8.0 min) |
| fastapi_14301 | resolved | 71 | 8 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=5 read_file=2 edit_file=1 get_status=1 submit_patch=1 |  |
| fastapi_14246 | no_patch | 225 | 98 |  | fastapi/_compat/v2.py | run_command=97 read_file=1 submit_patch=1 |  |
| fastapi_13713 | agent_error | 489 | 45 |  | fastapi/applications.py, fastapi/openapi/utils.py | read_file=27 run_command=18 edit_file=3 | Agent exceeded session timeout (8.0 min) |
| httpx_3672 | right_file_wrong_fix | 228 | 15 | src/ahttpx/_parsers.py, src/ahttpx/_server.py, src/httpx/_pa | src/ahttpx/_parsers.py, src/ahttpx/_pool.py, src/ahttpx/_ser | edit_file=8 read_file=6 skill:locate.py=1 submit_patch=1 |  |
| fastapi_15800 | no_patch | 225 | 99 |  | fastapi/applications.py, fastapi/routing.py | run_command=92 read_file=7 submit_patch=1 |  |
| fastapi_14371 | no_patch | 257 | 99 |  | fastapi/_compat/v2.py, fastapi/dependencies/utils.py, fastap | run_command=91 read_file=8 submit_patch=1 |  |
| fastapi_14605 | right_file_wrong_fix | 126 | 23 | fastapi/exceptions.py, fastapi/openapi/utils.py, fastapi/tem | fastapi/dependencies/utils.py, fastapi/exceptions.py, fastap | edit_file=12 run_command=6 read_file=5 get_status=1 submit_patch=1 |  |
| fastapi_13537 | resolved | 155 | 13 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=7 read_file=4 edit_file=2 get_status=1 submit_patch=1 |  |
| fastapi_14953 | right_file_wrong_fix | 319 | 8 | fastapi/datastructures.py | fastapi/_compat/v2.py, fastapi/datastructures.py | edit_file=28 read_file=4 run_command=3 get_status=1 submit_patch=1 |  |
| fastapi_14616 | resolved | 375 | 95 | fastapi/dependencies/utils.py | fastapi/dependencies/utils.py | run_command=82 read_file=12 edit_file=1 submit_patch=1 |  |
| rich_3772 | no_patch | 452 | 95 |  | rich/traceback.py | read_file=73 run_command=22 submit_patch=1 |  |
| rich_3518 | resolved | 319 | 11 | rich/table.py | rich/table.py | edit_file=34 read_file=4 run_command=3 write_file=2 skill:locate.py=1 |  |
| rich_3521 | right_file_wrong_fix | 335 | 94 | rich/segment.py | rich/segment.py | run_command=85 read_file=7 skill:locate.py=1 edit_file=1 submit_patch=1 |  |
| rich_3506 | agent_error | 483 | 15 |  | rich/segment.py | run_command=13 read_file=2 | Agent exceeded session timeout (8.0 min) |
| rich_2725 | wrong_location | 240 | 95 | repro.py, rich/box.py | rich/table.py | run_command=77 read_file=15 write_file=2 edit_file=1 submit_patch=1 |  |
| rich_3043 | resolved | 232 | 28 | .pre-commit-config.yaml, rich/_export_format.py | rich/_export_format.py | edit_file=14 run_command=13 read_file=13 get_status=1 submit_patch=1 |  |
| rich_3006 | resolved | 134 | 93 | rich/repr.py | rich/repr.py | run_command=91 read_file=1 edit_file=1 submit_patch=1 |  |

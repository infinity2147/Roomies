SUBMIT: submission_2026-10-07_c9e_analyzercap.zip

# Release 2026-10-07: PROVISIONAL (as of 05:30 IST; a later cycle finalizes it by about 11:30 IST with proxy evidence)

**Candidate:** C9e = C8 (LB 0.13 champion) + one change: a context cap on the `code_analyzer` sub-agent.
- The analyzer gets its own sampling config: max_output_tokens 4096 and thinking_budget 2048, instead of 8192 and 4096.
- The analyzer prompt gets a budget section:
  - at most 20 tool calls and reads of at most 60 lines;
  - no repeated identical calls;
  - a `sed -n` fallback when `read_file` returns the wrong lines;
  - at the cap, answer with `CONFIDENCE: low`.
- The root agent is unchanged.

**Why (DECISIONS D16):**
- On Prajna, the first 13 proxy tasks (C8 s1 + C9a s1) produced 4 tasks (31%) that died with `ContextWindowExceededError`.
- In all 4, the analyzer sub-agent was the last caller. It has no event compaction, and it ran 19–83 calls, one of them a 12× identical-read loop. The task then errors with an empty patch.
- The scorer runs the same harness code, so C8 very likely loses hidden tasks this way.

**Evidence so far:** the proxy benchmark is valid (gold 152/152, empty 0/152). The paired C9e vs C8 shards are queued at prio 11; read the latest numbers with `.venv/bin/python ops/queue/px_report.py`.

**Runtime:** the change can only make runs shorter, because the analyzer makes fewer calls. The 12-hour risk is no higher than C8's, and C8 completed.

**Alternatives (both packaged in this dir):**
- `submission_2026-10-07_c9a_editfix.zip`: C8 + edit-failure fallback.
- `submission_2026-10-07_c9b_reprofail.zip`: C8 + the repro must fail before editing.

**What the LB score teaches:** whether analyzer overflow costs hidden tasks. Expect +1 to +3 tasks if the 31% overflow rate is real on hidden repos and some of those tasks were solvable.

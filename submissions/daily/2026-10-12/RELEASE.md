SUBMIT: submission_2026-10-12_c23_t12.zip   (lead, 2026-10-12; smoke px_c23t12smoke_s1 PASSED: 2/3 solved, engine installed 3/3, 32 edits applied, 0 malformed calls, 1.9-6.1 min/task)

# C23_t12 = C9e with edits routed through a rule engine + 12-min per-task cap
- Change vs C9e: edit_file removed (Gemma-4 template dictsort + backtick bug made 78% of edit calls malformed, 27% of time);
  skill edit-engine installs /tmp/ae.py once; edits = run_command heredoc SEARCH/REPLACE (fuzzy match, syntax refusal,
  closest-lines hint, no identical resend). Fallback line: python heredoc edit if the install fails (skills never ran on the real scorer).
- Proxy (304 paired runs vs C9e s1-2): 0.385 vs 0.391 (-0.007, z -0.25) = equal accuracy; LLM calls -16%.
- L4 latency model (304 runs): 3.83 vs 4.92 min/task. 120 tasks with 12-min cap: 9.6 h (x1.3), 10.5 h (x1.45), 11.4 h (x1.6);
  solves lost to the cap ~2/117. C9e uncapped = 12.8-14.3 h (it hit Notebook Timeout).
- Purpose: (1) first runtime-safe submission of the C9e-level agent; (2) measure proxy->LB gap (C8 proxy 0.32 vs LB 0.13).
- Risk: skill execution on the real scorer untested (fallback line mitigates).

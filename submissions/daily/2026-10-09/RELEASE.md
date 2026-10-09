SUBMIT: submission_2026-10-09_c9e_analyzercap.zip

# Release 2026-10-09 (lead session): C9e = C8 + analyzer cap only (no eval_config, exactly like C8)
**Why this one.** Best non-thinking candidate on the proxy: C9e vs C8 +0.076 (n=304 paired, 2 seeds, sign-z +3.05);
better than C9ae (+0.053) and the capped variants (C9ae_t7 +0.003, C9ae_t5 −0.046). Thinking variants are much stronger on
the proxy (C15n512 +0.197) but 1.8× slower on L4 (≈18 h @120 tasks) and a time cap removes most of their gain.
**Runtime safety by construction.** Root agent byte-identical to C8 (system.md, agent.yaml, root sampling); C8 completed on the
scorer. Only the code_analyzer sub-agent changed: max_output_tokens 8192→4096, thinking budget 4096→2048, 20-call / 60-line
read budget in its prompt → it can only make runs shorter (and removes ContextWindowExceeded crashes, D16).
**Due diligence.** Validator OK; zip testzip OK; the 3 changed files are byte-identical to the ones C9ae ran on the Kaggle
4×L4 scorer stack (kernel c9ae-t30s: 30 tasks, completed, no crash); no eval_config (scorer defaults, as C8).
**Expected LB:** ≥ C8 (0.13); proxy suggests about +1 to +4 hidden tasks.

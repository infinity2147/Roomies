# LoRA adapter forensics — 2026-10-10

## Verdicts

| Adapter / candidate | Reported proxy | Verdict |
|---|---|---|
| **C19** `e3_distill_r128` (C9ae + d1) | 0.094 vs C9ae 0.328 (n=128) | **INVALID EVAL (serving issue).** All of it ran on A40s with a 6k-token KV cache. Re-eval enqueued. Secondary **data bug**: "thinking-off" targets contain thought channels (see §4). |
| **C18** `e2_nebius_r128` (C8 + e2) | 0.165–0.175 vs C8 0.310 | **PARTLY INVALID.** The 3 shards run on A40 (s2, s5, s7; 132 tasks) are invalid. On the 5 shards run on dgx (n=190, valid serving) it is a **mild genuine negative**: 0.242 vs C8 0.268 on the same shards. It roughly doubles call count, hits the 100-call budget on 41/190 tasks, and takes ~42 min/task. Reject on cost, not on "-0.135". |
| **mix_v1** `mix_v1_r128` | never evaluated | Export and serving are verified OK (NLL drops). Packaged as **C20** (C9ae + m1), eval-half re-eval enqueued. |

The adapters were trained correctly and exported/served correctly (§3). The catastrophic numbers come from the **serving config**.

## 1. Root cause: `--max-loras 8` drains the KV cache on an A40 at TP=1

`scripts/serve_vllm.sh` defaulted to `--max-loras 8 --max-lora-rank 128`. vLLM pre-allocates a full rank-128, all-linear LoRA buffer per slot (the adapter is 1.98 GB in bf16). With 8 slots on a 44 GiB A40 this leaves:

| vLLM log | adapter | node | KV memory | KV tokens | concurrency @32k |
|---|---|---|---|---|---|
| vllm_346962_0 (C19) | d1, max_loras 8 | cn32-a40 | **5.5 GiB** | **6,000** | 1.13x |
| vllm_346497/346759 (C18) | e2, max_loras 8 | a40 | 5.5 GiB | 6,000 | 1.13x |
| vllm_346001 (C18) | e2, max_loras 8 | cn16-dgx (80 GB) | 37.4 GiB | 40,816 | 7.7x |
| vllm_346760 (base) | none | a40 | 20.1 GiB | 21,984 | 4.15x |
| **lora_forensics/vllm_c19_maxlora1_347155** | d1, **max_loras 1** | cn34-a40 | **18.4 GiB** | **20,080** | 3.79x |

The workers run CONC=6 agents (plus analyzer sub-agents) against a cache that holds ~1 request of 6k tokens. The engine runs 1 request while 5 wait (`Running: 1 reqs, Waiting: 5 reqs`, vllm_346962_0.log 16:57) and preempts constantly. Per-LLM-call wall time:

| set | median LLM calls/task | median min/task | median s per LLM call | timeouts |
|---|---|---|---|---|
| C19, A40 (all) | 9 | 60.1 | **401** | 116/128 |
| C18, A40 shards s2/s5/s7 | 3 | 60.1 | **1202** | 119/132 |
| C18, dgx shards s0/1/3/4/6 | 131 | 41.8 | 15.5 | 32/190 |
| C8 base, same 5 shards | 73 | 6.8 | 6.2 | 3/190 |
| C9ae base eval-half | 50 | 9.2 | 6.9 | 22/170 |

Trace example (C19, attrs, `results/px/px_c19_distill_s1/e0/traces/trace_attrs_*.json`): analyzer calls with 39 completion tokens arrive at elapsed 441 s, then 1035 s. That is ~10 min of queueing for a 39-token answer.

**Hypotheses 1/5/6:**
- **(1) Degenerate generation: no.** C19 d1 calls have median 53 completion tokens, p95 415, max 1,789, and 0 hit 8k (base C9ae: 35 / 269). C18 e2 is somewhat degenerate: 206/34,703 calls hit the 8,192-token cap (base 3/17,189), and it loops to the 100-call budget.
- **(5) Serving: yes, dominant.** Base worker logs show no enforce-eager and CUDA graphs on. The LoRA punica kernels also halve single-stream decode: 17.0 tok/s for C19 with max_loras 1 vs 32.5 tok/s for base (`Running: 1 reqs` log lines). That is acceptable.
- **(6) Routing: correct.** The traces carry `model_name: d1` / `e2` on root calls and the base name on code_analyzer calls (by design). The 28-second run (`results/px/_bad_px_c19_run1`) was a server where `d1` never registered (404 "The model `d1` does not exist"), so it was correctly quarantined.

**Fix applied:** `scripts/serve_vllm.sh` now defaults `MAX_LORAS` to the number of adapters in `SERVE_SUB/adapters/` (an env override still works).

**Kaggle note:** the scorer uses `max_loras=8, max_lora_rank=128` (scripts/kaggle_eval/kernel_template.py:159) with TP up to 4. Per-GPU LoRA buffers are /TP there, but if the scorer runs on small GPUs the same KV squeeze could hit a LoRA submission. A Kaggle 4xL4 timing run is needed before shipping any adapter.

## 2. Proof the fix works (job 347155, a40, MAX_LORAS=1)

C19 on 3 eval-half tasks (`results/px/_sanity_c19_maxlora1_347155`):

| task | C19 before (s1/s2) | C19 max_loras=1 | base C9ae (s1/s2) |
|---|---|---|---|
| tqdm_1783 | 60.2 timeout / 60.2 timeout | **11.2 min, resolved** (25 calls) | 3.2 / 7.0 |
| marshmallow_3004 | 60.3 / 60.3 (resolved, 8–10 calls) | **6.1 min, resolved** (23 calls) | 1.6 / 2.4 |
| attrs_1571 | 60.1 / 60.1 timeouts | **10.1 min**, unresolved (101 calls) | 11.1 / 60.2 |

Per-task time is back in the ~10 min band, and outputs are sane (normal tool calls, patches submitted).

## 3. Export/serving correctness: base vs adapter NLL through vLLM

`results/lora_forensics/nll_check.py` computes masked-token NLL via vLLM `prompt_logprobs` on training-format sequences. It is an end-to-end check of export (k/v dup, module names, alpha/r) and serving on the int4 base. Output is in `results/lora_forensics/nll_{d1,m1,e2}_347155.jsonl`:

| adapter | sequence | NLL base | NLL adapter |
|---|---|---|---|
| d1 | click_3704 / click_3739 / click_3739 | 0.405 / 0.551 / 0.454 | 0.142 / 0.215 / 0.112 |
| m1 | hydra-2543 / pandas / Anexo2-11 | 1.140 / 0.879 / 1.369 | 0.295 / 0.336 / 0.658 |
| e2 | canvasapi-343 / borg-6528 / borg-7583 | 0.974 / 1.497 / 1.134 | 0.253 / 0.390 / 0.418 |

The NLL drop is 2.5–4x for all three adapters, so the exported weights are correct and applied (a broken k/v dup or wrong scaling would raise NLL or leave it flat). The training curves are healthy too (e2 0.50 to 0.30, mix 0.48 to 0.30, distill 0.13 to 0.056 over 2 epochs).

Caveats:
- These are in-sample sequences, so this only proves correctness, not generalisation.
- The vLLM base NLL is ~2x the step-0 training loss (e.g. e2 ~1.1 vs 0.50). This is probably a different sequence mix (the first-step loss averages other sequences), but it is worth one `train_lora --verify` comparison on the same sequence.

**(4) Export bug: none found.**

## 4. Data/format findings

- **(2/3) Distill data is not thinking-off:** 1,896 of 3,298 trained spans (57%) in `data/derived/sft/e3_distill_all.jsonl` start with a `<|channel>thought … <channel|>` block (token id 100). `render_segment` is called on `last["request"]["messages"]`. ADK echoes `reasoning_content` in history, and the Gemma-4 template renders it even with `enable_thinking=False`. So C19 was trained to emit thoughts while served thinking-off, which contradicts the design intent. The effect is visible but mild (d1 median completion 53 vs 39 tokens). It is not the cause of the timeouts.
  - **Fix** (not applied, needs a ~6 h dgx retrain): in `build_dataset.py` distill branch, strip reasoning before rendering, e.g. in `render_segment` build `msgs = [{k: v for k, v in m.items() if k not in ("reasoning_content", "reasoning")} for m in ...]` when `a.distill_thinking_off`. Then rebuild and retrain:
    ```
    .venv-harness/bin/python -m src.sft.build_dataset --capture results/capture --distill-thinking-off --out data/derived/sft/e3_distill_v2.jsonl
    # then edit ops/slurm/ap_train_distill.sbatch: --data e3_distill_v2.jsonl --out runs/lora/e3_distill_v2_r128, S=submissions/c19b_...
    ```
    (Use the same source set as e3_distill_all.)
  - Only do this if the C19 re-eval is within noise of C9ae. With 289 sequences from 43 tasks and 2 epochs (loss 0.056), overfitting is the bigger risk.
- **Loss mask:** the masked spans are assistant-generated only: thought + tool call + `<|tool_response>` stop, with the tool responses that follow unmasked (decoded example click_3704: 16 spans, 6,311/14,083 tokens). No user/tool tokens are trained.
- **"leak" column (D18):** this is cosmetic for grading. C9ae eval-half resolves 0.435/0.471 with leaked conftest/pytest.ini vs 0.393/0.537 without. C18 resolves 46 of 205 leaked patches.

## 5. What I ran / started

- Job 347137 (ap-lora-sanity): aborted. The NLL check OOMed the engine because prompt_logprobs materialise vocab-size logits at GPU_UTIL 0.92.
- Job 347155 (ap-lora-sanity, `results/lora_forensics/ap_lora_sanity.sbatch`): completed. Results are in §1–3.
- `scripts/serve_vllm.sh`: MAX_LORAS defaults to the adapter count.
- New `submissions/c20_c9ae_mix`: C9ae plus `adapters/m1` (a copy of runs/lora/mix_v1_r128/adapter), `adapter: m1`.
- Queues (eval half e0–e3 × s1/s2, 8 items each):
  - `ops/queue_lora_fix_c19`: runs `px_c19_ml1_s{1,2}`
  - `ops/queue_lora_fix_c20`: runs `px_c20_mix_ml1_s{1,2}`
- Workers:
  - **347180** `ap-worker-c19fix` (APQ=ops/queue_lora_fix_c19, SERVE_SUB=c19, MAX_LORAS=1)
  - **347181** `ap-worker-c20fix` (APQ=ops/queue_lora_fix_c20, SERVE_SUB=c20, MAX_LORAS=1)
  - Both are a40x2, about 4–6 h.
- Old `ops/queue_lora_d1/parked` items are left untouched and should be dropped: their results used the broken config.

## 6. Next commands

```
# check the fix took effect in the new workers (expect ~20,080 tokens, NOT 6,000)
grep -h "GPU KV cache size" results/slurm/vllm_347180_*.log results/slurm/vllm_347181_*.log
# harvest when 8/8 items done in each queue
.venv/bin/python ops/queue/px_report.py --base c9ae_evalhalf   # compare px_c19_ml1 / px_c20_mix_ml1 vs px_c9ae_evalhalf (paired, n=85x2)
# C18: optional clean re-run of the invalid A40 shards only (s2,s5,s7) with the fixed script, if E2 is still of interest
```

Decision rule: an adapter is a candidate only if it is ≥ +0.03 vs C9ae on the eval half and min/task ≤ 1.3x base. Shipping one additionally needs a Kaggle 4xL4 timing check (scorer max_loras=8).

# Training plan: E1 LoRA on `gemma-4-31b-it-qat-w4a16-ct` (Training Engineer, 2026-10-02)

**Question.** How do we train a LoRA that vLLM 0.19.1 loads and applies to the W4A16 QAT checkpoint
*with the same function it had in training*, and what compute does E1 (~100–400 rejection-sampled
trajectories of 10–30k tokens) need?

**Answer.**
1. Train against the competition checkpoint itself, with the int4 weights frozen and dequantized
   on the fly. The base weights are then bit-identical to what vLLM multiplies with.
2. Export PEFT-named adapters, and copy the `k_proj` LoRA to `v_proj` on the 10 global
   (`k_eq_v`) layers. Without that copy, vLLM serves a different function from the one trained.
3. One 300×20k×2-epoch run fits on **1×80 GB GPU** at 32k context. It takes about 2–3 h on an
   H100 or 6–9 h on an A100 80GB, and costs well under $50 per run. Training is cheap; the
   §8 evaluation runs are what cost GPU time.

Code: `src/sft/train_lora.py` (new). The CPU self-test `--tiny` passes (log below).

---

## 1. Options to get a trainable base (facts first)

| Option | What it is | Base the LoRA sees vs what vLLM serves | Memory (weights) | Verdict |
|---|---|---|---|---|
| **A. Frozen int4 from the ct checkpoint, dequant on the fly** (`--weights int4`, default) | `PackedInt4Linear` keeps `weight_packed` (int32) + `weight_scale` (bf16), rebuilds W in fwd/bwd | **Identical**. Our dequant == compressed-tensors' `PackedQuantizationCompressor.decompress`, max\|diff\| = 0.0 on 4 real modules (incl. a global layer) | **18.0 GiB** text stack (checkpoint header, incl. 2.6 GiB bf16 embedding) | **Recommended** |
| B. Same checkpoint dequantized once at load (`--weights bf16`, or HF `from_pretrained`) | dense bf16 nn.Linear | Identical | ≈57 GiB (29.3B linear params ×2 B + embedding) | Faster per step, but needs >80 GB at 32k (H200/B200, or 2×80 GB with `--layer-devices`) |
| C. `google/gemma-4-31B-it-qat-q4_0-unquantized` (bf16 QAT weights, HF) | QAT weights *before* int4 rounding | Mismatch = int4 rounding error per weight. The LoRA learns on a base that is never served | 62 GB download + 57 GiB | Worse than A/B, and no benefit |
| D. `google/gemma-4-31B-it` (bf16, non-QAT; exists on HF) | Different weights (no QAT fine-tune) | Largest mismatch | 62 GB | Reject |
| E. QLoRA (bitsandbytes NF4 / Unsloth) | Re-quantizes the weights to NF4 | Different quantization grid from the served int4. The Unsloth discussion says the QAT calibration cannot be preserved this way ([unsloth#6389](https://github.com/unslothai/unsloth/discussions/6389)) | ~18 GiB | Reject. bnb and peft are not installed anyway |

Evidence for these choices:
- **transformers 5.13.1 + compressed-tensors 0.15.0 always decompress.** `CompressedLinear.from_linear` now
  raises "no longer supported" (`compressed_tensors/linear/compressed_linear.py`). The HF quantizer loads
  `weight_packed/scale/shape` through `DecompressExperts` into dense `weight`
  (`transformers/quantizers/quantizer_compressed_tensors.py:get_weight_conversions`;
  `transformers/integrations/compressed_tensors.py`). So HF `from_pretrained` gives option B (bf16, ~57 GiB
  text plus the vision tower), not a frozen-int4 QLoRA. That is why `train_lora.py` has its own loader for option A.
- The checkpoint is symmetric int4, `group_size` 32, `pack-quantized`, `lm_head` and vision ignored
  (`external/models/.../config.json`). The scales are bf16, so `int4 × bf16 scale` is exact in one
  rounding. Our dequant is therefore bit-exact, not merely close.
- vLLM's W4A16 kernels also multiply bf16 activations by these same dequantized values. vLLM applies the
  LoRA as a separate bf16 punica term (`vllm/lora/`), which is what we train. The only expected residual
  is GEMM accumulation-order noise (about 1e-3 relative). This is a hypothesis; the parity test in §4 measures it.

## 2. Adapter format that vLLM 0.19.1 accepts (verified in code)

- **Keys:** `base_model.model.model.language_model.layers.{L}.{self_attn|mlp}.{q,k,v,o,gate,up,down}_proj.lora_{A,B}.weight`.
  Shapes are A `[r, in]` and B `[out, r]`, in bf16. `adapter_config.json` follows PEFT; vLLM requires
  `use_dora=false` and `modules_to_save=null` (`vllm/lora/peft_helper.py`).
  - `parse_fine_tuned_lora_name` strips `base_model.model.`.
  - `Gemma4ForConditionalGeneration.hf_to_vllm_mapper` maps `model.language_model.` → `language_model.model.`
    (`vllm/model_executor/models/gemma4_mm.py:905`).
  - `verify_adapter()` in `train_lora.py` runs **vLLM's own functions** on every key and asserts the
    expected module path.
- **Packing:** the `packed_modules_mapping` of both Gemma4 classes is `qkv_proj=[q,k,v]` and `gate_up_proj=[gate,up]`.
  `_create_merged_loras_inplace` (`vllm/lora/model_manager.py:632`) packs separate q/k/v (gate/up) LoRAs
  into one `PackedLoRALayerWeights`. A missing sub-module becomes `None`, meaning no delta on that slice.
  Separate q/k/v adapters are therefore merged correctly.
- **Bug I found: global (`k_eq_v`) layers.**
  - What the code does: on the 10 `full_attention` layers (5, 11, …, 59) the checkpoint has no `v_proj`.
    - HF training uses `value_states = key_states`, i.e. the raw `k_proj` output (`modeling_gemma4.py:1264`).
      A `k_proj` LoRA therefore changes **both K and V**.
    - vLLM builds a `qkv_proj` for these layers too and copies the *base* `k_proj` weights into the V slot
      (`vllm/.../gemma4.py:1651-1660`). That copy happens only in the weight loader; LoRA is not duplicated.
      So a `k_proj` LoRA reaches only the K slice in vLLM.
  - Consequence: without a fix, a trained adapter's V on the global layers differs between train and serve.
  - Fix: the exporter writes a copy of each `k_proj` LoRA as `v_proj` on those layers. This is the default;
    `--no-dup-kv` turns it off.
  - The `--tiny` test checks this numerically under vLLM's semantics (dense base, V slot = base K plus the
    v-LoRA). Logit diff vs the training model is **1.9e-5 with the copy and 15.3 without it**.
  - `verify_adapter` rejects adapters that lack the copy. It flags the existing smoke adapter
    (`submissions/lora_smoke/adapters/smoke`: names and shapes pass, then "layer 35: k_proj LoRA without
    matching v_proj copy"). That is harmless for a random smoke adapter, but it would have silently
    degraded a trained one.
- **Limits:** scorer `max_lora_rank=128`, `max_loras=8` (`scripts/kaggle_eval/kernel_template.py:109`).
  The verifier asserts `r ≤ 128`. At r=16 over all 7 projections there are 122.4M params, and the adapter
  file is about 247 MB in bf16.

## 3. Memory and compute (300 seq × 20k tokens × 2 epochs = 12M tokens)

**Memory, option A, r=16, layer-wise gradient checkpointing, batch 1, loss on trained positions only:**

| Item | 16k tokens | 32k tokens |
|---|---|---|
| int4 text weights (measured) | 18.0 GiB | 18.0 GiB |
| LoRA params + grads + AdamW (fp32, 122M) | 2.0 | 2.0 |
| Checkpointed layer inputs (T×5376×2 B×60) | 9.8 | 19.7 |
| Recompute peak of one layer (MLP 21504-wide acts + grads) | ~4–5 | ~8–10 |
| Attention masks (bool T², sliding + full) | 0.5 | 2 |
| Loss chunk (2048×262144 fp32 logits + grad) | ~4 | ~4 |
| **Total (estimate)** | **~40 GiB** | **~55–60 GiB** |

The loss is computed in chunks only at trained positions. Full 32k×262k fp32 logits would take 34 GB.
Option B adds about 39 GiB, giving roughly 95 GiB at 32k (does not fit 80 GB).

**FLOPs per token**, all estimates:
- Linear forward: 2×29.3B = 58.6 GF.
- Attention forward: sliding layers ≈1.7 GF; global layers ≈6.6 GF at 20k.
- Training cost ≈ forward + recompute + backward of activation grads only (the base is frozen)
  ≈ **215 GF/token**.
- 12M tokens → **2.6e18 FLOP per run**.
- Dequant overhead (3 × 29B elementwise ops per sequence) is negligible next to that.

| Hardware | Fits | Effective TFLOPS (25–40% MFU; hypothesis) | Hours/run | ≈ Cost/run* | LORO 3 folds + final (≈3× a full run) |
|---|---|---|---|---|---|
| 1× H100 80GB | 32k ✓ | 250–400 | **1.8–2.9** | $5–10 | 6–9 h, $15–30 |
| 1× H200 141GB | 32k ✓ (B too) | 250–400 | 1.8–2.9 | $7–12 | 6–9 h |
| 1× A100 80GB | 32k ✓ | 80–125 | **5.7–9** | $8–16 | 17–27 h, $25–50 |
| 1× L40S/A6000 48GB | ≤16k only | 70–110 | 6.5–10 | ~$7–10 | data >16k must be dropped |
| 2× A5000 24GB (this box) | ≤~8k via `--layer-devices` | ~35 (one GPU active at a time) | ~20 | — | Not viable: shared GPUs, truncates most data |
| Kaggle T4×2 / P100 | ✗ (16 GB/GPU, no bf16 on T4) | — | — | — | Not viable |

\*On-demand prices of about $2–3.5 per H100-hour and $1.3–1.8 per A100-hour; these are assumptions,
so check your provider. Multiple GPUs don't help one run much at this data size. Use them to train
the LORO folds **in parallel**: 4 GPUs give all 4 adapters in about 3 h.

## 4. Recommended recipe

- **Data:** `src/sft/build_dataset.py` JSONL. These are exact per-call prompts split at ADK compaction
  boundaries, with loss on assistant spans only, including the `<|tool_response>` and `<turn|>` stop tokens.
  - Sources: rejection-sampled passes from the frozen C6a scaffold (pass `--tasks-file` covering
    tasks.jsonl and mined_tasks.jsonl so mined trajectories are keyed).
  - Keep at most 2–3 distinct passing trajectories per task, preferring shorter ones. Count by
    trajectory, not by segment.
  - Apply the PLAN.md §9 hygiene filters.
  - **Mined tasks:** 66 tasks, of which **62 are rich and 4 are fastapi**. In the rich fold they are all
    removed with the held-out repo, so that fold trains on fastapi + requests (+4 mined) only. Expect
    the rich fold to be the hardest; it is also the most honest test of transfer.
- **LoRA:** r=16, α=32 (scale 2), dropout 0.05, targets q,k,v,o,gate,up,down on all 60 layers.
- **Optimizer:** AdamW, lr 1e-4, wd 0, warmup 5%, cosine to 10%, clip 1.0.
  - grad-accum 8 sequences, giving about 38 steps per epoch for 300 sequences.
  - 2 epochs (≈75 optimizer steps).
  - Token-normalized loss (`--loss-norm token`).
- **Sequence length:** `--max-tokens 32768`, the same as the scorer's `max_model_len`. No packing.
  Train with the same `enable_thinking` setting the submission uses; E0 data uses thinking off.
- **Fallbacks:**
  - If held-out NLL rises after epoch 1, use 1 epoch or lr 5e-5.
  - If held-out pass@1 is flat while training repos improve, try r=8, attention-only targets, or more mined data.

**Exact commands** (on the training GPU box, same Python stack as `.venv-harness`: torch 2.10,
transformers 5.13.1, compressed-tensors 0.15, safetensors, accelerate; no peft or bnb needed):
```bash
# 0. CPU self-test (already passes here)
.venv-harness/bin/python -m src.sft.train_lora --tiny [--check-real-dequant] [--tiny-dtype bf16]
# 1. preflight on the GPU: peak memory + tok/s at 32k; also confirms SDPA handles global head_dim=512
python -m src.sft.train_lora --preflight --seq-len 32768        # fallback: --attn flex_attention
# 2. dataset (once rejection-sampled runs with capture.jsonl exist)
.venv-harness/bin/python -m src.sft.build_dataset --runs <run dirs...> --out data/derived/sft/e1.jsonl \
    --tasks-file <tasks.jsonl + mined_tasks.jsonl concatenated> --max-tokens 32768
# 3. LORO folds (run in parallel, one GPU each) + final
for R in fastapi rich requests; do
  python -m src.sft.train_lora --data data/derived/sft/e1.jsonl --holdout-repo $R --out runs/e1_lo_$R \
      --rank 16 --alpha 32 --lr 1e-4 --epochs 2 --grad-accum 8 --save-every-epoch
done
python -m src.sft.train_lora --data data/derived/sft/e1.jsonl --out runs/e1_all --epochs 2 --save-every-epoch
# 4. verify (also runs automatically at the end of training)
.venv-harness/bin/python -m src.sft.train_lora --verify runs/e1_all/adapter
# 5. ship: copy runs/e1_all/adapter/* -> submissions/<new>/adapters/e1/ and set `adapter: e1` in agent.yaml
```
Each run writes `train_log.jsonl` (loss, lr, grad-norm, tok, peak GiB), held-out NLL per epoch,
`run_args.json` (train/held-out ids), and `adapter/` (+ `epochN/`).

## 5. Validation plan

1. **Format gate (CPU, done):** `--tiny` and `verify_adapter` check names, shapes, rank ≤ 128,
   vLLM name mapping, and the k_eq_v copy.
2. **Serve/train parity (1 GPU-hour, when GPUs are free):**
   - Serve with `scripts/serve_vllm.sh <submission_with_adapter>`.
   - Request `prompt_logprobs` for 3 training sequences, with and without the LoRA.
   - Compare them with the trainer's per-token log-probs.
   - Pass if mean |Δlogprob| between trainer and vLLM on trained tokens is < 10% of the LoRA effect
     (|Δ| between base and adapter). This is the only test that covers the real kernels; do it before
     any §8 run.
3. **Cheap model selection:** held-out-repo masked NLL per epoch (built in), used to pick the epoch
   checkpoint. It does not replace pass@1.
4. **§8 protocol:** each fold adapter on its held-out repo's tasks, ≥4 seeds, pass@1 mean ± std,
   pass@k, stable/stochastic, time/task, tool-error rate.
   - Compare paired against C6a on the same tasks (McNemar / paired bootstrap, p < 0.05).
   - Gate E: E1 > C6a beyond noise, time/task not worse, no single-repo collapse. On 30 tasks one
     standard error is ±2.5 tasks, so only gains of about 5 tasks or more are detectable per fold.
   - The final submission adapter is trained on everything; its only check is the parity + format gate
     plus one Kaggle sanity run.

## 6. Risks

| Risk | Status / mitigation |
|---|---|
| QAT + LoRA base mismatch | Removed by option A (base bit-exact). Residual kernel noise is measured by parity test 5.2 |
| k_eq_v V-path mismatch in vLLM | **Found and fixed** in the exporter; the verifier enforces it |
| SDPA with global head_dim 512 at 32k (flash-SDPA only supports ≤256; a math fallback would need ~64 GB of T² scores) | Unverified hypothesis that the mem-efficient backend handles it. Run `--preflight` first; fall back to `--attn flex_attention` or cap at 16k |
| Overfitting (≈75 steps, 100–200 distinct tasks, fastapi 52% of real tasks) | Held-out NLL per epoch, LORO, at most 2–3 trajectories per task, 1-epoch fallback |
| LoRA decode overhead in vLLM (punica) increases time/task, so more timeouts | Measure time/task in §8. Shorter trajectories in training data also help |
| Data/format drift (empty-thought 3-token difference on first turn, `reports/e0_sft_format.md`; thinking mode) | Train and serve with the same scaffold and the same `enable_thinking` |
| `--layer-devices` multi-GPU split | Implemented but **untested** (CPU only here). Prefer one 80 GB GPU per fold |

## 7. What the user must arrange

- **1–4 × 80 GB GPUs** (H100 preferred, A100 80GB acceptable) for roughly 3–10 GPU-hours per LORO set.
  The machine needs ≥64 GB RAM, ≥60 GB disk, and CUDA 12.8 drivers.
- On it: a copy of `external/models/gemma-4-31b-it-qat-w4a16-ct/` (23 GB), the repo, and the
  `.venv-harness` stack.
- Separately, GPU time for the §8 evaluations, which costs more than training. Local A5000s are suitable
  for serving and parity checks only.

## Evidence log (commands run)

- `CUDA_VISIBLE_DEVICES="" .venv-harness/bin/python -m src.sft.train_lora --tiny --check-real-dequant`:
  - dequant vs compressed-tensors reference: 0.0 on the tiny model and 0.0 on the real layers 0 and 5.
  - LORO fold: rich + mined_rich held out.
  - masked loss over the first 3 / last 3 steps: 19.35 → 0.20; held-out NLL 20.3 → 10.1.
  - 28 keys (incl. v_proj copy on layer 1) verified via vLLM's parser.
  - k_eq_v logit diff 1.86e-05 vs 15.3 without the copy. **PASS**.
  - `--tiny-dtype bf16` also **PASSES**: logit diff 0.41 (bf16 model vs fp32 reference) vs 11.2 without the copy.
- `--verify submissions/lora_smoke/adapters/smoke`: names and shapes OK; rejected for the missing k_eq_v v_proj copy.
- Checkpoint header: text stack 17.97 GiB, other tensors 3.70 GiB; layer 5 is global (q 16384×5376, k 2048×5376, no v).
- `nvidia-smi` (read-only): 2× RTX A5000 24 GB.

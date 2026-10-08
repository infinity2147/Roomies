# LoRA / PEFT for multi-turn SWE agents (31B, int4-QAT frozen base) - research notes (2024-2026)

Scope note: ~17 tool calls; several primary PDFs were unreadable (binary) so I used arXiv HTML where possible. Items marked "(snippet)" come from search-result summaries, not the paper body.

## 1. Rank, target modules, LoRA vs full FT, "learns less / forgets less"

### Takeaway
Evidence says: target all linear layers incl. MLP (attention-only underperforms), use alpha=2r (or rsLoRA-like scaling) for high rank, LoRA LR ~10x full-FT LR, and code needs high rank (r>=64, ideally 256) for SFT, while RL needs very low rank. Every open SWE-agent SFT recipe I found except SWE-Gym's 32B Moatless run used FULL fine-tuning, so there is almost no direct evidence for LoRA-SFT on SWE agents.

### Cited Findings
- Biderman et al.: on code IFT/CPT, LoRA substantially underperforms full FT at standard low ranks, but forgets less (avg HellaSwag/ARC/Winogrande: code IFT full FT 0.414 vs LoRA r=64 0.509; code CPT 0.545 vs 0.617 at r=256) - [arXiv 2405.09673](https://arxiv.org/html/2405.09673v2)
- Same paper: ranks 16/64/256 on all modules, alpha=2r "crucial for high ranks" (standard alpha/r shrinks high-rank updates); Attention-only targeting underperforms MLP or All; ranks 16-64 were insufficient for code; full-FT weight perturbation has rank 10-100x typical LoRA ranks (mostly in MLPs); recommendations: all modules, r=256 if memory allows, alpha=2r, sweep LR 1e-5..5e-4 and take highest stable - [arXiv 2405.09673](https://arxiv.org/html/2405.09673v2)
- Same paper LRs: code IFT LoRA 2e-4 (r=16/64), 1e-4 (r=256, since 2e-4 spiked); sweep best LoRA 5e-4 (code) vs full FT 5e-5 - [arXiv 2405.09673](https://arxiv.org/html/2405.09673v2)
- Thinking Machines "LoRA Without Regret" (Sep 2025): optimal LoRA LR ~10x FullFT (~15x for ~100-step runs); with 1/r scaling optimal LR is roughly rank-independent; LoRA less tolerant of large batch (recommend effective batch <32); attention-only underperforms, include MLP; rank-1 matches FullFT in RL (policy gradient ~1 bit/episode); TRL guide suggests rank 1-32 for RL - [TRL doc](https://huggingface.co/docs/trl/main/en/lora_without_regret), [summary](https://www.beri.net/learning/thinking-machines-lora-without-regret). Claims are lab-internal; no independent replication found.
- SWE-Gym: Moatless 32B policy/verifier trained with LoRA rank 64 via Unsloth on 1xH100, LR 5e-4, batch 8, 5 epochs, 10k ctx; OpenHands verifier LoRA (Unsloth) reached 29.8@8 vs 27.2@8 for full-param verifier - [arXiv 2412.21139](https://arxiv.org/html/2412.21139)
- Open SWE SFT recipes use full FT: SWE-Lego (Qwen3-32B, LLaMA-Factory, LR 5e-5, 4 epochs, bs 64, cosine, warmup 0.1, wd 0.01, 128k ctx YaRN) [arXiv 2601.01426](https://arxiv.org/html/2601.01426); SERA (Qwen3-32B, Axolotl, LR 1e-5, wd 0.01, 3 epochs, 32,768 ctx) [arXiv 2601.20789](https://arxiv.org/html/2601.20789v2); SWE-Gym OpenHands (torchtune, LR 1e-4, <=5 ep, bs 8, 32k ctx, 2-8 H100) [arXiv 2412.21139](https://arxiv.org/html/2412.21139); Nebius RFT (LR 5e-6 cosine, 1 epoch, bs 64, 65k ctx, AdamW wd 0.1, 10 warmup) [arXiv 2508.03501](https://arxiv.org/html/2508.03501v2)
- Controlled tool-calling study used LoRA r=32, alpha=64, max 2 epochs, assistant-turn loss only, citing LoRA preserves capabilities (snippet) - [arXiv 2609.17848](https://arxiv.org/pdf/2609.17848)

### Inferences
- With a 31B base and ~1k windows, LoRA r=128 all-linear, alpha=256 (2r), LR ~1e-4 to 2e-4 (lower, ~5e-5 to 1e-4, if loss spikes at r>=128 per Biderman) is a defensible, literature-consistent setup. Full-FT LRs for 32B SFT are 1e-5 to 5e-5, so 10x gives 1e-4 to 5e-4.
- Because LoRA is less tolerant of large batches, prefer small effective batch (8-32 windows) over 64+; with 1,000 windows that is ~30-125 steps, so LR/warmup matter a lot.
- Expect a gap vs full FT on skills requiring large behavioral shift; the "forgets less" property is useful for format retention but also means 1 epoch on 1k windows may under-learn - consider 2-3 epochs (SERA 3, SWE-Lego 4, SWE-Gym up to 5 on full FT).
- K=V sharing on global layers: no literature found; copying k_proj LoRA to v_proj is an implementation choice to verify numerically (compare logits with adapter served vs trained).

### Gaps
- No paper found directly comparing LoRA vs full FT on SWE-agent SFT at 30B+.
- SWE-smith's training hyperparameters (LR, epochs, LoRA/full) not obtained (appendix F.1 not read). Skywork-SWE, SWE-Dev hyperparameters not retrieved.
- No evidence on K=V-tied attention LoRA.

## 2. Variants: DoRA, rsLoRA, PiSSA, LoRA+, LoRA-GA, QLoRA on QAT base

### Takeaway
When LR (and batch size) are tuned per method, variants show no systematic advantage over vanilla LoRA (within ~1-2%). Nothing agent- or QAT-specific found. Spend effort on LR/alpha, not variants.

### Cited Findings
- "Learning Rate Matters: Vanilla LoRA May Suffice" (ICML 2026): with large HP searches on math and code, all variants peak at similar performance (within 1-2%); preferred LRs differ (e.g., 10x between PiSSA and LoRA), so shared settings mislead - [arXiv 2602.04998](https://arxiv.org/html/2602.04998v1)
- "Beware of the Batch Size": batch size explains conflicting variant results; tuned vanilla LoRA often matches variants - [arXiv 2602.09492](https://arxiv.org/pdf/2602.09492)
- Unified LoRA variants study exists (includes DoRA, rsLoRA, LoRA+) but I could not read comparative numbers - [arXiv 2601.22708](https://arxiv.org/pdf/2601.22708)
- Biderman: alpha=2r with standard scaling is needed at high rank - [arXiv 2405.09673](https://arxiv.org/html/2405.09673v2); rsLoRA (alpha/sqrt(r)) addresses the same issue (from memory, not re-verified this session).
- QLoRA merge pitfalls: adapters trained against dequantized weights lose accuracy when merged into the 4-bit base; workaround is to merge in higher precision then requantize, or keep adapter separate - [Kaitchup](https://kaitchup.substack.com/p/qlora-merging-pitfalls-dont-lose)

### Inferences
- Your design (adapter kept separate, served by vLLM on the int4 base, trained against on-the-fly-unpacked int4) matches the "do not merge" advice and avoids requant error. Main risk is train/serve mismatch: ensure the training-time dequantization equals vLLM's int4 kernel numerics (verify with a logit/perplexity comparison).
- DoRA adds overhead (norm computation) and vLLM adapter support for DoRA is uncertain (not checked); skip.

### Gaps
- Nothing found on LoRA over QAT int4 specifically (torchao/Gemma QAT docs not checked) or LoRA-GA/LoRA+ on agents/code. PiSSA/LoRA-GA require SVD/gradient init of a quantized base - impractical here (inference).

## 3. Loss design

### Takeaway
Assistant-only loss plus masking of malformed/erroring turns (regex-detected) is consistently beneficial (+2-3 pts SWE-Lego; +1.3 SRFT). Keep full context for masked steps.

### Cited Findings
- SWE-Lego: error messages from terminal identified by regex; loss masked on the agent responses causing them (invalid function call/args); errors from reproducing bugs or running tests NOT masked. Ablation resolve rate 8B/32B: both 42.2/52.6; masking only 41.8/51.8; curriculum only 40.2/50.4; neither 39.4/48.8 - [arXiv 2601.01426](https://arxiv.org/html/2601.01426)
- SWE-Lego curriculum: difficulty = trajectory length (r=-0.95 with resolve rate), 3 bins by turns (0-50, 50-70, 70-100), 3 stages each cumulative (include earlier data); beat model-based difficulty by 0.5 - same source
- Nebius RFT: assistant turns that triggered environment-formatting errors are masked - [arXiv 2508.03501](https://arxiv.org/html/2508.03501v2)
- JetBrains Step Rejection FT (arXiv 2605.10674): all trajectories kept in context; resolved steps weight 1; for unresolved trajectories a critic LLM (Claude 4 Sonnet, ~$660 per 5,000 trajs) marks harmful steps, weight 0. SWE-smith SWE-agent data, Qwen2.5-Coder-32B: base 7.0, naive distill 28.5, RFT 30.9, SRFT 32.2 (+1.3, CI [0.4,2.3]); masking both splits 29.4. Harmful steps 4.1% of resolved, 7.1% of unresolved. LR/epochs/LoRA not reported - [arXiv HTML](https://arxiv.org/html/2605.10674), [JetBrains blog](https://blog.jetbrains.com/research/2026/06/step-rejection-fine-tuning/)
- SERA: truncated long trajectories with ordered truncation (43.00%) beat random (37.47%); best truncation ratio ~0.95; prioritize trajectories <=32k - [arXiv 2601.20789](https://arxiv.org/html/2601.20789v2)
- Off-policy prefix handling: SGCD masks the policy-segment prefix from action supervision but keeps it as context (snippet) - [arXiv 2606.18890](https://arxiv.org/pdf/2606.18890)

### Inferences
- For your 24k windows cut from longer trajectories: keep earlier turns as context with zero loss weight; put loss on later turns (so each turn is trained once across overlapping windows, avoiding double counting).
- Mask: turns whose tool call fails parse/schema validation in YOUR scaffold, plus turns causing format errors; do not mask test/repro failures.
- Per-trajectory vs per-token normalization: not found in cited sources. Per-token (sum over all assistant tokens / total tokens in batch) is standard; long trajectories dominate. A hedge is token-mean within the packed batch; test is cheap.
- Thinking/reasoning tokens: SWE-Lego text did not say how handled (not found). Decision depends on whether deployment uses thinking; match deployment template exactly and include thinking tokens in loss only if the served model emits them.

### Gaps
- No quantitative evidence for per-trajectory normalization or thinking-token inclusion; curriculum evidence only from SWE-Lego (full FT, Qwen3).

## 4. Data recipes (RFT, mixing, counts, epochs, LRs)

### Takeaway
Gains come from thousands of validated trajectories; performance scaled log-ish with data without saturation up to ~5-18k. ~1k windows is at the low end (SWE-Gym got +13.6 Verified points from 491). Mixing own+external ratios: no published ratio found.

### Cited Findings
- SWE-Gym: 491 successful trajectories (gpt-4o/claude-3.5-sonnet; ~19 turns, ~19k tokens avg) took Qwen2.5-Coder-32B from 7.0 -> 20.6 Verified (3.0 -> 15.3 Lite); +868 on-policy trajectories used for self-improvement; Moatless 32B self-improvement saturated after 1 iteration (19.0 -> 19.7); no saturation with data - [arXiv 2412.21139](https://arxiv.org/html/2412.21139)
- SWE-smith: 5,016 trajectories (Claude 3.7 Sonnet teacher, SWE-agent, 75 steps) chosen from 6,457; cap of 3 trajectories per task instance because easy repeatedly-solved tasks hurt; 36% of 17,906 attempts resolved; SWE-agent-LM-32B 40.2 Verified; performance ~log in number of repos - [arXiv 2504.21798](https://arxiv.org/html/2504.21798v2)
- SWE-Lego: 32k task instances, ~18k validated trajectories (14.1k resolved + 4.0k semi-resolved); Qwen3-32B 52.6 Verified (58.8 TTS@16), SFT only - [arXiv 2601.01426](https://arxiv.org/html/2601.01426)
- SERA: SFT-only; Sera-4.6-Lite ~36k T1 + 36k T2; Qwen3-32B 49.5 (32k ctx) / 54.2 (64k); repo specialization with ~8,000 trajectories per repo (3k soft-verified + 5k filtered); power-law scaling R^2>0.95 - [arXiv 2601.20789](https://arxiv.org/html/2601.20789v2); [MarkTechPost](https://www.marktechpost.com/2026/01/30/ai2-releases-sera-soft-verified-coding-agents-built-with-supervised-training-only-for-practical-repository-level-automation-workflows/)
- Skywork-SWE: >8,000 validated trajectories, 10,169 instances, Qwen2.5-Coder-32B, 38.0 Verified (47.0 with TTS); no saturation - [arXiv 2506.19290](https://arxiv.org/pdf/2506.19290)
- Nebius: Qwen2.5-72B, 6,548 successful trajectories (10 samples per task), 1 epoch RFT -> ~20%; DAPO RL -> 39% - [arXiv 2508.03501](https://arxiv.org/pdf/2508.03501), [MarkTechPost](https://www.marktechpost.com/2025/08/12/nebius-ai-advances-open-weight-llms-through-reinforcement-learning-for-capable-swe-agents/); Nebius OpenHands dataset: 67,074 Qwen3-Coder-480B trajectories, RFT checkpoints 50.3% (30B), 61.7% (235B) - [Nebius blog](https://nebius.com/blog/posts/openhands-trajectories-with-qwen3-coder-480b)
- Mixed-data practice: keep successful own rollouts, filter external data for schema validity, keep off-policy prefixes as context only, iterate (snippets) - [arXiv 2606.18890](https://arxiv.org/pdf/2606.18890), [arXiv 2602.11220](https://arxiv.org/pdf/2602.11220)
- SWE-Dev, other hyperparameters: not found.

### Inferences
- Your ~16M-token / ~1,000-window pilot is similar in trajectory count to SWE-Gym's 491 (gains were large from a weak base) but you have a stronger base; expect smaller delta. Cap per-task duplicates (SWE-smith: <=3) and drop trivially easy ones.
- Epochs: published full-FT recipes use 3-5 epochs on 5-18k trajectories; Nebius used 1 epoch on 6.5k at a conservative LR 5e-6. With LoRA on 1k windows, 2-3 epochs at LR ~1e-4 is plausible but must be validated on a held-out scaffold-fidelity eval.
- RFT on own rollouts: SWE-Gym saw diminishing returns after 1 iteration; use own successes as a minority (my suggestion: 20-40%) mainly to anchor format/style; no ratio evidence exists.

### Gaps
- No published own:external mixing ratio; no data-size vs LoRA-rank study for agents.

## 5. Format drift / forgetting; keeping scaffold exact

### Takeaway
Primary mitigations: train with the exact deployment chat template and tool schema, mask malformed turns, filter external data by schema, keep LoRA (forgets less), and gate on a format-validity metric.

### Cited Findings
- Format is a major failure mode: base Qwen2.5-72B scored ~11% mostly due to poor command formatting; RFT lifted to ~20% - [arXiv 2508.03501](https://arxiv.org/pdf/2508.03501), [MarkTechPost](https://www.marktechpost.com/2025/08/12/nebius-ai-advances-open-weight-llms-through-reinforcement-learning-for-capable-swe-agents/)
- SWE-Lego used post-hoc fixes for common tool-call errors and restricted tool set (bash, str_replace_editor, think, finish) (secondary) - [review](https://www.themoonlight.io/en/review/swe-lego-pushing-the-limits-of-supervised-fine-tuning-for-software-issue-resolving)
- Filtering by action parseability, function-name correctness and argument consistency against tool schemas before SFT (snippet) - [arXiv 2609.17848](https://arxiv.org/pdf/2609.17848)
- LoRA forgets less than full FT - [arXiv 2405.09673](https://arxiv.org/html/2405.09673v2)

### Inferences
- Convert external OpenHands trajectories into the exact rendered prompt string (chat template tokens, tool-call syntax) the deployed scaffold uses; run a parse-validator on every assistant turn; reject/mask failures. Evaluate adapter by tool-call parse rate on rollouts, not just loss.

### Gaps
- No quantitative study on tool-call-format forgetting under LoRA at 30B found.

## 6. RL with LoRA on agents (GRPO/DAPO/GSPO)

### Takeaway
SWE-agent RL at scale used full-parameter training on large clusters; LoRA-RL evidence is rank-1/low-rank, mostly non-SWE. Feasibility on ~20 inference GPUs + few A100s is marginal for a 31B model.

### Cited Findings
- DeepSWE-Preview: Qwen3-32B, RL only, 4.5K R2E-Gym problems, 64 H100 for 6 days, 512 parallel containers, LR 1e-6, batch 64, 65k ctx; 23 -> 42% in 200 steps; 59% with TTS - [Together](https://together.ai/blog/deepswe), [rLLM docs](https://rllm-project.readthedocs.io/en/latest/examples/swe/) (context-length inconsistent between sources)
- Nebius DAPO: full-parameter, 128 H200 (16x8), LR 1e-6, group 10, 65k then 131k ctx, 300 problems/iter, clip (0.2,0.3)/(0.2,0.26), max turns 40/80 -> 39% - [arXiv 2508.03501](https://arxiv.org/html/2508.03501v2)
- LoRA RL: rank-1 matches FullFT in RL (TML); SkyRL supports Tinker API with LoRA (skyrl-tx), published recipe Qwen3-4B LoRA rank 1 on 8 H100 - [TRL](https://huggingface.co/docs/trl/main/en/lora_without_regret), [MarkTechPost](https://www.marktechpost.com/2025/11/03/anyscale-and-novasky-team-releases-skyrl-tx-v0-1-0-bringing-tinker-compatible-reinforcement-learning-rl-engine-to-local-gpu-clusters/), [SkyRL](https://github.com/NovaSky-AI/SkyRL)
- Rollout-pass-rate-control paper uses GRPO++ with verl on Qwen3-32B R2E-Gym (settings: clip-high 0.28, no KL) - [arXiv 2605.05112](https://arxiv.org/pdf/2605.05112)
- CodeScout and GSPO-with-LoRA on SWE agents: not found.

### Inferences
- A LoRA-RL loop on 31B is attractive for memory (rank 8-32; policy served by vLLM with the LoRA adapter, as you already do). Rollout cost dominates: DeepSWE-scale = ~4.5k tasks x multiple rollouts at 40-80 turns; ~20 inference GPUs gives roughly 1/3 of DeepSWE's 64 GPUs. A smaller-scale run (few hundred tasks, group 8, 1e-5-ish LoRA LR per 10x rule, i.e. DeepSWE 1e-6 x 10) is feasible but unproven; trainer throughput (60-110 tok/s per A100) is the bottleneck: a batch of 64 trajectories x 20k tokens = 1.3M tokens = ~3.5-6 A100-hours per step per GPU.
- Cheaper alternative with evidence: iterated RFT/SRFT on own rollouts (SWE-Gym saw saturation after 1 round, Nebius went RFT -> RL for 2x).

### Gaps
- No LoRA+GRPO SWE results at 30B found; SkyRL SWE LoRA numbers not found.

## 7. Throughput on A100-80GB for 31B

### Takeaway
Realistic LoRA training on a 31B dense/int4-dequant model on one A100 is ~100-150 tok/s at long context; your measurement (60-110) is plausible. Biggest levers: fused/chunked cross-entropy (large Gemma vocab), shorter windows, DP over multiple A100s, and avoiding recompute where possible.

### Cited Findings
- Liger Kernel: fused linear cross-entropy never materializes full logits; README claims +20% throughput, -60% memory (LLaMA-3-8B, bs 8, FSDP1, 8xA100, grad ckpt); HF OOM at 4K vs Liger 16K in that benchmark; memory freed can allow turning off grad checkpointing/offload; gains are for full-FT cluster setups, not verified for single-GPU LoRA - [arXiv 2410.10989](https://arxiv.org/pdf/2410.10989), [GitHub](https://github.com/linkedin/Liger-Kernel)
- Logit memory example: 16,384 tokens x 129,280 vocab ~40 GB (third-party estimate) - [Forgather](https://forgather.readthedocs.io/en/latest/fused_loss/fused_cross_entropy_comparison/)
- Packing + Liger together: not found.
- Other cited throughput: your own measurement; 16M tokens at 33 h implies ~135 tok/s average (my arithmetic), above the 60-110 range, so check numbers.

### Inferences
- Gemma has a ~262k vocab (my knowledge, not verified this session); at 24k tokens fp32 logits would be ~25 GB, so chunked/fused CE (Liger or equivalent) is likely a top win for memory, enabling larger windows or fewer checkpointed layers.
- Data parallel with LoRA: 4 A100s with 4 independent adapter copies and gradient all-reduce of tiny LoRA gradients gives near-linear scaling (frozen int4 base 16-20 GB per GPU); this is the most reliable ~Nx speedup. Dequantize-once caching to bf16 is infeasible for 31B (~62 GB) alongside activations at 24k; per-layer cache in grad-ckpt recompute is the compromise (untested).
- Packing: your windows are already near-full length, so packing yields little; avoid padding waste by bucketing. Shorter windows (16k) cut attention cost quadratically but lose long-horizon context; SERA found ordered truncation at ~0.95 coverage works best.
- FlashAttention-2/3 or SDPA flash for long context is assumed; sliding-window layers help Gemma-type models.

### Gaps
- No published tokens/s for 30B+ LoRA on A100 with 24k sequences found; no source for dequantize-once caching or int4-QAT training speed.

"""Fix vLLM 0.19.1 Gemma4 pipeline-parallel path (only used locally; the Kaggle scorer runs TP=4).

Bugs: (1) non-first PP ranks call IntermediateTensors.get(), which doesn't exist;
(2) the last layer returns residual=None (Gemma4 folds the residual into hidden_states) and the 31B
model has no per-layer embeddings, so the tensors sent between stages contain None.
Layers ignore the incoming residual, so sending zeros is numerically identical.

Usage: .venv-harness/bin/python scripts/patch_vllm_gemma4_pp.py   (idempotent)
"""

from pathlib import Path

import vllm

path = Path(vllm.__file__).parent / "model_executor" / "models" / "gemma4.py"
src = path.read_text()
MARK = "# [gemma_rl PP patch]"

# (3) Per-rank KV cache size: env GEMMA_RL_KV_GIB_PER_RANK="4.2,1.5" overrides kv_cache_memory_bytes
# per (global) rank, so an uneven PP split on partly occupied GPUs can size each stage's cache.
wpath = Path(vllm.__file__).parent / "v1" / "worker" / "gpu_worker.py"
wsrc = wpath.read_text()
if MARK not in wsrc:
    old_kv = "        if kv_cache_memory_bytes := self.cache_config.kv_cache_memory_bytes:\n"
    new_kv = (
        f"        {MARK}\n"
        "        import os as _os\n"
        "        _per = _os.environ.get('GEMMA_RL_KV_GIB_PER_RANK')\n"
        "        if _per:\n"
        "            self.cache_config.kv_cache_memory_bytes = int(float(_per.split(',')[self.rank]) * 2**30)\n"
        + old_kv
    )
    assert wsrc.count(old_kv) == 1, "vLLM gpu_worker changed; re-check patch"
    wpath.write_text(wsrc.replace(old_kv, new_kv))
    print("patched:", wpath)

# (4) Local context is smaller than the scorer's 32k: instead of rejecting prompt + max_tokens >
# max_model_len, only reserve GEMMA_RL_MIN_OUTPUT_RESERVE tokens for output when validating the prompt;
# get_max_tokens() then clamps the request's max_tokens to the remaining context.
ppath = Path(vllm.__file__).parent / "renderers" / "params.py"
psrc = ppath.read_text()
if MARK not in psrc:
    old_p = "        return self.max_total_tokens - self.max_output_tokens\n"
    new_p = (
        f"        {MARK}\n"
        "        import os as _os\n"
        "        _res = _os.environ.get('GEMMA_RL_MIN_OUTPUT_RESERVE')\n"
        "        if _res:\n"
        "            return self.max_total_tokens - min(self.max_output_tokens, int(_res))\n"
        + old_p
    )
    assert psrc.count(old_p) == 1, "vLLM renderers/params changed; re-check patch"
    ppath.write_text(psrc.replace(old_p, new_p))
    print("patched:", ppath)

if MARK in src:
    print("already patched:", path)
    raise SystemExit(0)

old_get = 'per_layer_inputs = intermediate_tensors.get("per_layer_inputs")'
new_get = f'per_layer_inputs = intermediate_tensors.tensors.get("per_layer_inputs")  {MARK}'
old_ret = """            return IntermediateTensors(
                {
                    "hidden_states": hidden_states,
                    "residual": residual,
                    "per_layer_inputs": per_layer_inputs,
                }
            )"""
new_ret = f"""            {MARK}
            _t = {{
                "hidden_states": hidden_states,
                "residual": residual if residual is not None else torch.zeros_like(hidden_states),
            }}
            if per_layer_inputs is not None:
                _t["per_layer_inputs"] = per_layer_inputs
            return IntermediateTensors(_t)"""
assert src.count(old_get) == 1 and src.count(old_ret) == 1, "vLLM source changed; re-check patch"
path.write_text(src.replace(old_get, new_get).replace(old_ret, new_ret))
print("patched:", path)

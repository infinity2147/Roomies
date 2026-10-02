"""P3: build a PEFT LoRA adapter for gemma-4-31b-it-qat-w4a16-ct without training, to test that
adapters load (locally + Kaggle) and change outputs. Shapes are read from the checkpoint, so the
same code is the template for real adapters' tensor naming.

Usage: .venv-harness/bin/python -m src.sft.make_smoke_adapter --out submissions/lora_smoke/adapters/smoke \
          [--rank 16] [--scale 0.02] [--layers all|0,1,2] [--modules q,k,v,o,gate,up,down] [--zero_b]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file

MODEL = Path(__file__).resolve().parents[2] / "external" / "models" / "gemma-4-31b-it-qat-w4a16-ct"
MODS = {"q": "self_attn.q_proj", "k": "self_attn.k_proj", "v": "self_attn.v_proj", "o": "self_attn.o_proj",
        "gate": "mlp.gate_proj", "up": "mlp.up_proj", "down": "mlp.down_proj"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--scale", type=float, default=0.02, help="std of B (A is ~N(0, 1/sqrt(in)))")
    ap.add_argument("--layers", default="all")
    ap.add_argument("--modules", default="q,k,v,o,gate,up,down")
    ap.add_argument("--zero_b", action="store_true", help="B=0: adapter is a no-op (like the sample)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    cfg = json.loads((MODEL / "config.json").read_text())["text_config"]
    n_layers = cfg["num_hidden_layers"]
    layers = range(n_layers) if a.layers == "all" else [int(x) for x in a.layers.split(",")]
    mods = [MODS[m] for m in a.modules.split(",")]
    g = torch.Generator().manual_seed(a.seed)
    tensors: dict[str, torch.Tensor] = {}
    with safe_open(MODEL / "model.safetensors", "pt") as f:
        keys = set(f.keys())
        for L in layers:
            for m in mods:
                sk = f"model.language_model.layers.{L}.{m}.weight_shape"
                if sk not in keys:
                    continue  # e.g. global-attention layers have no v_proj (k_eq_v)
                out_f, in_f = f.get_tensor(sk).tolist()
                pre = f"base_model.model.model.language_model.layers.{L}.{m}"
                A = torch.randn(a.rank, in_f, generator=g) / in_f**0.5
                B = torch.zeros(out_f, a.rank) if a.zero_b else torch.randn(out_f, a.rank, generator=g) * a.scale
                tensors[f"{pre}.lora_A.weight"] = A.to(torch.bfloat16).contiguous()
                tensors[f"{pre}.lora_B.weight"] = B.to(torch.bfloat16).contiguous()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    save_file(tensors, out / "adapter_model.safetensors")
    target = sorted({m.split(".")[-1] for m in mods})
    (out / "adapter_config.json").write_text(json.dumps({
        "base_model_name_or_path": "google/gemma-4-31b-it-qat-w4a16-ct", "bias": "none", "fan_in_fan_out": False,
        "inference_mode": True, "init_lora_weights": True, "lora_alpha": a.alpha, "lora_dropout": 0.0,
        "modules_to_save": None, "peft_type": "LORA", "r": a.rank, "target_modules": target,
        "task_type": "CAUSAL_LM", "use_dora": False, "use_rslora": False,
        "layers_to_transform": None if a.layers == "all" else list(layers),
    }, indent=1))
    size = sum(t.numel() * 2 for t in tensors.values()) / 2**20
    print(f"wrote {out} tensors={len(tensors)} size={size:.1f} MiB rank={a.rank} targets={target}")


if __name__ == "__main__":
    main()

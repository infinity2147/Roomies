"""E1: LoRA SFT for gemma-4-31b-it-qat-w4a16-ct, exported in the exact adapter format vLLM 0.19.1 loads.

Design (see reports/council/training_plan.md for the evidence behind each choice):
  * Base weights = the competition checkpoint itself. Every quantized nn.Linear of the text stack is
    replaced by PackedInt4Linear, which keeps the int4 `weight_packed` + bf16 `weight_scale` tensors
    (~18 GiB for the whole text model) and dequantizes on the fly in forward/backward. The
    dequantized values are bit-identical to compressed-tensors' own decompression, i.e. to the weights
    vLLM's W4A16 kernels multiply with, so there is no train/serve base mismatch.
    `--weights bf16` instead dequantizes once at load (~57 GiB; faster per step, needs >80 GB).
  * Text-only Gemma4ForCausalLM (transformers 5.13); vision/audio towers are never loaded.
  * Plain LoRA (PEFT-equivalent math: y = W x + alpha/r * B A dropout(x)), params in fp32.
    PEFT is not installed in .venv-harness, so LoRA is implemented here; the exported files use
    PEFT's naming/config so vLLM's PEFTHelper + LoRAModel load them unchanged.
  * Masked causal-LM loss on loss_mask==1 tokens only (JSONL from src/sft/build_dataset.py),
    computed in chunks on the trained positions only (full 32k x 262k logits would need 34 GB),
    with final_logit_softcapping=30 applied exactly as in the model.
  * Gradient checkpointing per decoder layer, batch = 1 sequence, no packing, grad accumulation.
  * k_eq_v fix: on full-attention layers the checkpoint has no v_proj and HF uses V = k_proj(x), so a
    k_proj LoRA changes K *and* V during training. vLLM packs these layers into qkv_proj with the
    base K weights copied into the V slot but applies the k_proj LoRA only to the K slice. The
    exporter therefore writes a copy of each such k_proj LoRA as v_proj (`--no-dup-kv` disables);
    `--tiny` proves numerically that this reproduces the training-time function under vLLM's
    packing semantics, and that omitting it does not.
  * LORO: `--holdout-repo fastapi|rich|requests|httpx` drops every sequence whose repo (instance_id
    prefix, `mined_` stripped) matches, and reports held-out NLL on them.

Usage:
  # CPU self-test (tiny random Gemma4 incl. a k_eq_v global layer; no big weights touched)
  .venv-harness/bin/python -m src.sft.train_lora --tiny
  # memory/throughput preflight on the training GPU (random tokens, 2 steps)
  python -m src.sft.train_lora --preflight --seq-len 32768
  # real LORO fold
  python -m src.sft.train_lora --data data/derived/sft/e1.jsonl --holdout-repo rich \
      --out runs/e1_rich --rank 16 --alpha 32 --lr 1e-4 --epochs 2 --grad-accum 8
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
import struct
import tempfile
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "external" / "models" / "gemma-4-31b-it-qat-w4a16-ct"
PROJ = {"q": "self_attn.q_proj", "k": "self_attn.k_proj", "v": "self_attn.v_proj", "o": "self_attn.o_proj",
        "gate": "mlp.gate_proj", "up": "mlp.up_proj", "down": "mlp.down_proj"}
CKPT_PREFIX = "model.language_model."  # Gemma4ForConditionalGeneration checkpoint / adapter naming
ADAPTER_PREFIX = "base_model.model.model.language_model.layers."
KEY_RE = re.compile(r"^base_model\.model\.model\.language_model\.layers\.(\d+)\.(self_attn|mlp)\."
                    r"(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)\.lora_(A|B)\.weight$")
MAX_LORA_RANK = 128  # Kaggle scorer: enable_lora=True, max_loras=8, max_lora_rank=128


# ----------------------------------------------------------------------------- int4 base weights

def dequant_int4(packed: torch.Tensor, scale: torch.Tensor, in_features: int, group_size: int) -> torch.Tensor:
    """compressed-tensors pack-quantized (symmetric int4, group strategy) -> dense, in scale.dtype.
    Nibble i of packed column j is column 8*j+i, stored with +8 offset (helpers.unpack_from_int32)."""
    out = packed.shape[0]
    shifts = torch.arange(0, 32, 4, device=packed.device, dtype=torch.int32)
    q = ((packed.unsqueeze(-1) >> shifts) & 0xF).reshape(out, -1)[:, :in_features] - 8
    w = q.to(scale.dtype).view(out, in_features // group_size, group_size) * scale.unsqueeze(-1)
    return w.view(out, in_features)


class _Int4MatMul(torch.autograd.Function):
    """y = x W^T with W rebuilt from int4 in forward and again in backward (never stored)."""

    @staticmethod
    def forward(ctx, x, packed, scale, in_features, group_size):
        ctx.save_for_backward(packed, scale)
        ctx.meta = (in_features, group_size)
        return F.linear(x, dequant_int4(packed, scale, in_features, group_size).to(x.dtype))

    @staticmethod
    def backward(ctx, g):
        packed, scale = ctx.saved_tensors
        w = dequant_int4(packed, scale, *ctx.meta).to(g.dtype)
        return g @ w, None, None, None, None


class PackedInt4Linear(nn.Module):
    def __init__(self, in_features: int, out_features: int, group_size: int, device=None):
        super().__init__()
        self.in_features, self.out_features, self.group_size = in_features, out_features, group_size
        self.register_buffer("weight_packed", torch.empty(out_features, math.ceil(in_features / 8),
                                                          dtype=torch.int32, device=device))
        self.register_buffer("weight_scale", torch.empty(out_features, in_features // group_size,
                                                         dtype=torch.bfloat16, device=device))

    def forward(self, x):
        return _Int4MatMul.apply(x, self.weight_packed, self.weight_scale, self.in_features, self.group_size)


class LoRALinear(nn.Module):
    def __init__(self, base: nn.Module, r: int, alpha: float, dropout: float):
        super().__init__()
        self.base = base
        dev = next(base.buffers(), None)
        dev = dev.device if dev is not None else next(base.parameters()).device
        self.lora_A = nn.Parameter(torch.empty(r, base.in_features, dtype=torch.float32, device=dev))
        self.lora_B = nn.Parameter(torch.zeros(base.out_features, r, dtype=torch.float32, device=dev))
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))  # PEFT default init (B=0 => no-op at start)
        self.scaling = alpha / r
        self.drop = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    @property
    def in_features(self):
        return self.base.in_features

    @property
    def out_features(self):
        return self.base.out_features

    def forward(self, x):
        y = self.base(x)
        return y + (self.drop(x) @ self.lora_A.to(x.dtype).t() @ self.lora_B.to(x.dtype).t()) * self.scaling


# ----------------------------------------------------------------------------- checkpoint loading

def _ckpt_files(model_dir: Path) -> list[Path]:
    idx = model_dir / "model.safetensors.index.json"
    if idx.exists():
        return sorted({model_dir / f for f in json.loads(idx.read_text())["weight_map"].values()})
    return [model_dir / "model.safetensors"]


def _header(path: Path) -> dict:
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return json.loads(f.read(n))


def text_config_of(model_dir: Path):
    from transformers.models.gemma4.configuration_gemma4 import Gemma4TextConfig
    cfg = json.loads((model_dir / "config.json").read_text())
    return Gemma4TextConfig(**cfg["text_config"]), cfg.get("quantization_config")


def k_eq_v_layers(tc) -> set[int]:
    if not getattr(tc, "attention_k_eq_v", False):
        return set()
    return {i for i, t in enumerate(tc.layer_types) if t == "full_attention"}


def load_text_model(model_dir: Path, device: str, dtype: torch.dtype, weights: str = "int4",
                    attn: str = "sdpa", layer_devices: list[str] | None = None):
    """Gemma4ForCausalLM (text stack only) from a compressed-tensors Gemma4ForConditionalGeneration
    checkpoint. weights='int4': PackedInt4Linear (frozen int4); 'bf16': dequantize once at load."""
    from safetensors import safe_open
    from transformers.models.gemma4.modeling_gemma4 import Gemma4ForCausalLM, Gemma4TextRotaryEmbedding

    tc, qc = text_config_of(model_dir)
    tc._attn_implementation = attn
    tc.use_cache = False
    w = qc["config_groups"]["group_0"]["weights"]
    assert (qc["format"], w["num_bits"], w["symmetric"], w["strategy"], w["type"]) == \
        ("pack-quantized", 4, True, "group", "int"), f"unsupported quantization config {qc}"
    gs = w["group_size"]
    n_layers = tc.num_hidden_layers
    if layer_devices:  # naive layer split across GPUs (untested here; use only for --weights bf16 on 2x80GB)
        per = math.ceil(n_layers / len(layer_devices))
        ldev = [layer_devices[min(i // per, len(layer_devices) - 1)] for i in range(n_layers)]
    else:
        ldev = [device] * n_layers

    def dev_of(local: str) -> str:
        m = re.match(r"model\.layers\.(\d+)\.", local)
        if m:
            return ldev[int(m.group(1))]
        return ldev[-1] if local.startswith("model.norm") else ldev[0]

    with torch.device("meta"):
        model = Gemma4ForCausalLM(tc)
    model.to(dtype)
    files = _ckpt_files(model_dir)
    keys = {k: f for f in files for k in _header(f) if k != "__metadata__"}
    # swap quantized linears for PackedInt4Linear / dense placeholders
    for name, mod in list(model.named_modules()):
        if isinstance(mod, nn.Linear) and CKPT_PREFIX + name.removeprefix("model.") + ".weight_packed" in keys:
            parent, child = name.rsplit(".", 1)
            if weights == "int4":
                new = PackedInt4Linear(mod.in_features, mod.out_features, gs, device="meta")
            else:
                new = nn.Linear(mod.in_features, mod.out_features, bias=False, device="meta", dtype=dtype)
            setattr(model.get_submodule(parent), child, new)
    model.to_empty(device=device)
    if layer_devices:
        for i, layer in enumerate(model.model.layers):
            layer.to(ldev[i])
        model.model.norm.to(ldev[-1])
    state = {**dict(model.named_parameters()), **dict(model.named_buffers())}
    loaded: set[str] = set()
    for f in files:
        with safe_open(f, "pt", device="cpu") as st:
            for k in st.keys():
                if not k.startswith(CKPT_PREFIX):
                    continue  # vision / audio / embed_vision
                local = "model." + k[len(CKPT_PREFIX):]
                if local.endswith(".weight_shape"):
                    mod = model.get_submodule(local.rsplit(".", 1)[0])
                    out_f, in_f = st.get_tensor(k).tolist()
                    assert (mod.out_features, mod.in_features) == (out_f, in_f), (k, out_f, in_f)
                    continue
                if weights == "bf16" and local.endswith((".weight_packed", ".weight_scale")):
                    if local.endswith(".weight_packed"):
                        base = k[: -len(".weight_packed")]
                        mod = model.get_submodule(local.rsplit(".", 1)[0])
                        wt = dequant_int4(st.get_tensor(k), st.get_tensor(base + ".weight_scale"), mod.in_features, gs)
                        mod.weight.data.copy_(wt.to(mod.weight.device))
                        loaded.add(local.rsplit(".", 1)[0] + ".weight")
                    continue
                t = state[local]
                t.data.copy_(st.get_tensor(k).to(t.device))
                loaded.add(local)
    # tie lm_head, rebuild non-persistent buffers that to_empty() left uninitialized
    model.lm_head.weight = model.model.embed_tokens.weight
    loaded.add("lm_head.weight")
    model.model.rotary_emb = Gemma4TextRotaryEmbedding(tc, device=ldev[0])
    model.model.embed_tokens.embed_scale.fill_(model.model.embed_tokens.scalar_embed_scale)
    persistent = {n for n, _ in model.named_parameters()} | set(model.state_dict().keys())
    missing = sorted(n for n in persistent if n not in loaded)
    assert not missing, f"not loaded from checkpoint: {missing[:10]} (+{len(missing) - 10})"
    for p in model.parameters():
        p.requires_grad_(False)
    if layer_devices:
        from accelerate.hooks import AlignDevicesHook, add_hook_to_module
        for i, layer in enumerate(model.model.layers):
            add_hook_to_module(layer, AlignDevicesHook(execution_device=ldev[i], io_same_device=False))
        add_hook_to_module(model.model.norm, AlignDevicesHook(execution_device=ldev[-1]))
    return model


def add_lora(model, targets: list[str], r: int, alpha: float, dropout: float, layers: list[int] | None = None) -> list[str]:
    names = []
    suffixes = {PROJ[t] for t in targets}
    for name, mod in list(model.named_modules()):
        m = re.fullmatch(r"model\.layers\.(\d+)\.(self_attn|mlp)\.(\w+_proj)", name)
        if not m or f"{m.group(2)}.{m.group(3)}" not in suffixes or mod is None:
            continue
        if layers is not None and int(m.group(1)) not in layers:
            continue
        parent, child = name.rsplit(".", 1)
        setattr(model.get_submodule(parent), child, LoRALinear(mod, r, alpha, dropout))
        names.append(name)
    return names


# ----------------------------------------------------------------------------- adapter export / verify

def export_adapter(model, out: Path, r: int, alpha: float, dup_kv: bool = True,
                   base_name: str = "google/gemma-4-31b-it-qat-w4a16-ct") -> dict:
    tc = model.config
    tensors: dict[str, torch.Tensor] = {}
    for name, mod in model.named_modules():
        if isinstance(mod, LoRALinear):
            pre = ADAPTER_PREFIX + name.removeprefix("model.layers.")
            tensors[pre + ".lora_A.weight"] = mod.lora_A.detach().to(torch.bfloat16).cpu().contiguous()
            tensors[pre + ".lora_B.weight"] = mod.lora_B.detach().to(torch.bfloat16).cpu().contiguous()
    n_dup = 0
    if dup_kv:
        for L in sorted(k_eq_v_layers(tc)):
            k = f"{ADAPTER_PREFIX}{L}.self_attn.k_proj"
            v = f"{ADAPTER_PREFIX}{L}.self_attn.v_proj"
            if k + ".lora_A.weight" in tensors and v + ".lora_A.weight" not in tensors:
                for s in ("lora_A", "lora_B"):
                    tensors[f"{v}.{s}.weight"] = tensors[f"{k}.{s}.weight"].clone()
                n_dup += 1
    from safetensors.torch import save_file
    out.mkdir(parents=True, exist_ok=True)
    save_file(tensors, out / "adapter_model.safetensors")
    targets = sorted({KEY_RE.match(k).group(3) for k in tensors})
    cfg = {"base_model_name_or_path": base_name, "bias": "none", "fan_in_fan_out": False,
           "inference_mode": True, "init_lora_weights": True, "lora_alpha": alpha, "lora_dropout": 0.0,
           "modules_to_save": None, "peft_type": "LORA", "r": r, "target_modules": targets,
           "task_type": "CAUSAL_LM", "use_dora": False, "use_rslora": False, "layers_to_transform": None}
    (out / "adapter_config.json").write_text(json.dumps(cfg, indent=1))
    return {"tensors": len(tensors), "dup_kv_layers": n_dup, "targets": targets,
            "MiB": sum(t.numel() * 2 for t in tensors.values()) / 2**20}


def verify_adapter(adapter_dir: Path, model_dir: Path = MODEL) -> dict:
    """Names, shapes and config vs the checkpoint, plus vLLM's own name parsing/mapping."""
    from safetensors import safe_open
    from safetensors.torch import load_file
    cfg = json.loads((adapter_dir / "adapter_config.json").read_text())
    r = cfg["r"]
    assert cfg["peft_type"] == "LORA" and not cfg["use_dora"] and not cfg["modules_to_save"], cfg
    assert r <= MAX_LORA_RANK, f"rank {r} > scorer max_lora_rank {MAX_LORA_RANK}"
    tensors = load_file(adapter_dir / "adapter_model.safetensors")
    tc, _ = text_config_of(model_dir)
    kv = k_eq_v_layers(tc)
    shapes = {}
    files = _ckpt_files(model_dir)
    for f in files:
        with safe_open(f, "pt", device="cpu") as st:
            for k in st.keys():
                if k.startswith(CKPT_PREFIX) and k.endswith(".weight_shape"):
                    shapes[k[len(CKPT_PREFIX):-len(".weight_shape")]] = tuple(st.get_tensor(k).tolist())
    try:
        from vllm.lora.utils import parse_fine_tuned_lora_name
        from vllm.model_executor.models.gemma4_mm import Gemma4ForConditionalGeneration as V
        mapper, how = V.hf_to_vllm_mapper, "vllm"
    except Exception as e:  # pragma: no cover
        parse_fine_tuned_lora_name, mapper, how = None, None, f"vllm import failed: {e!r}"
    for k, t in tensors.items():
        m = KEY_RE.match(k)
        assert m, f"bad key {k}"
        L, blk, proj, ab = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        mod = f"layers.{L}.{blk}.{proj}"
        if mod not in shapes:
            assert proj == "v_proj" and L in kv, f"{k}: no such module in checkpoint"
            shp = shapes[f"layers.{L}.self_attn.k_proj"]  # vLLM fills the V slot with K's weights
        else:
            shp = shapes[mod]
        out_f, in_f = shp
        want = (r, in_f) if ab == "A" else (out_f, r)
        assert tuple(t.shape) == want, f"{k}: {tuple(t.shape)} != {want}"
        assert t.dtype == torch.bfloat16, k
        if parse_fine_tuned_lora_name:
            vname, is_a = parse_fine_tuned_lora_name(k, mapper)
            assert vname == f"language_model.model.layers.{L}.{blk}.{proj}" and is_a == (ab == "A"), (k, vname)
    for L in kv:  # k_eq_v consistency: V LoRA must equal K LoRA (see module docstring)
        kk, vv = f"{ADAPTER_PREFIX}{L}.self_attn.k_proj.lora_A.weight", f"{ADAPTER_PREFIX}{L}.self_attn.v_proj.lora_A.weight"
        if kk in tensors:
            assert vv in tensors and torch.equal(tensors[kk], tensors[vv]), f"layer {L}: k_proj LoRA without matching v_proj copy"
    return {"keys": len(tensors), "rank": r, "name_check": how, "targets": cfg["target_modules"]}


# ----------------------------------------------------------------------------- data

def repo_of(instance_id: str) -> str:
    return instance_id.removeprefix("mined_").split("_")[0]


def load_data(path: Path, holdout_repo: str | None, max_tokens: int, exclude_ids: set[str] = frozenset()):
    train, held = [], []
    for line in open(path):
        ex = json.loads(line)
        if ex["instance_id"] in exclude_ids or len(ex["input_ids"]) > max_tokens or sum(ex["loss_mask"][1:]) == 0:
            continue
        (held if holdout_repo and repo_of(ex["instance_id"]) == holdout_repo else train).append(ex)
    return train, held


# ----------------------------------------------------------------------------- loss / train

def _ce_chunk(h, y, W, cap):
    logits = F.linear(h, W).float()
    if cap:
        logits = torch.tanh(logits / cap) * cap
    return F.cross_entropy(logits, y, reduction="sum")


def masked_loss(model, ex: dict, device: str, chunk: int = 2048):
    """Sum of CE over tokens t with loss_mask[t]==1 (predicted from position t-1), and their count."""
    ids = torch.tensor(ex["input_ids"], device=device)
    mask = torch.tensor(ex["loss_mask"], device=device)
    h = model.model(input_ids=ids[None], use_cache=False).last_hidden_state[0]
    pos = (mask[1:] > 0).nonzero().squeeze(1)
    hs, ys = h[pos].to(model.lm_head.weight.device), ids[pos + 1].to(model.lm_head.weight.device)
    cap = model.config.final_logit_softcapping
    total = h.new_zeros((), dtype=torch.float32)
    for s in range(0, len(pos), chunk):
        total = total + checkpoint(_ce_chunk, hs[s:s + chunk], ys[s:s + chunk], model.lm_head.weight, cap,
                                   use_reentrant=False)
    return total, len(pos)


@torch.no_grad()
def eval_nll(model, exs, device) -> float:
    was = model.training
    model.eval()
    s = n = 0
    for ex in exs:
        l, k = masked_loss(model, ex, device)
        s, n = s + l.item(), n + k
    model.train(was)
    return s / max(n, 1)


def train(a) -> tuple[nn.Module, dict]:
    torch.manual_seed(a.seed)
    random.seed(a.seed)
    dtype = {"bf16": torch.bfloat16, "fp32": torch.float32}[a.dtype]
    model = load_text_model(Path(a.model), a.device, dtype, a.weights, a.attn,
                            a.layer_devices.split(",") if a.layer_devices else None)
    lora = add_lora(model, a.targets.split(","), a.rank, a.alpha, a.dropout)
    if a.grad_ckpt:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.train()
    params = [p for n, p in model.named_parameters() if "lora_" in n]
    print(f"LoRA modules={len(lora)} params={sum(p.numel() for p in params) / 1e6:.2f}M", flush=True)
    exclude = set(Path(a.exclude_ids).read_text().split()) if a.exclude_ids else set()
    tr, held = load_data(Path(a.data), a.holdout_repo, a.max_tokens, exclude)
    assert tr, "no training sequences"
    print(f"train seqs={len(tr)} tokens={sum(len(e['input_ids']) for e in tr)} "
          f"trained={sum(sum(e['loss_mask']) for e in tr)} | holdout[{a.holdout_repo}] seqs={len(held)}", flush=True)
    steps_per_epoch = math.ceil(len(tr) / a.grad_accum)
    total = steps_per_epoch * a.epochs if not a.max_steps else a.max_steps
    opt = torch.optim.AdamW(params, lr=a.lr, betas=(0.9, 0.999), weight_decay=a.weight_decay)
    warm = max(1, int(a.warmup * total))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: (s + 1) / warm if s < warm else
                                              0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total - warm))))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "train_log.jsonl", "a")
    stats = {"train_ids": sorted({e["instance_id"] for e in tr}), "holdout_ids": sorted({e["instance_id"] for e in held}),
             "step_losses": [], "holdout_nll": []}
    if held:
        stats["holdout_nll"].append(eval_nll(model, held, a.device))
        print(f"holdout NLL before: {stats['holdout_nll'][-1]:.4f}", flush=True)
    step = 0
    t0 = time.time()
    for ep in range(a.epochs):
        order = tr[:]
        random.Random(a.seed + ep).shuffle(order)
        for g in range(0, len(order), a.grad_accum):
            group = order[g:g + a.grad_accum]
            n_tok = sum(sum(e["loss_mask"][1:]) for e in group)
            gl = 0.0
            for ex in group:
                l, k = masked_loss(model, ex, a.device)
                norm = n_tok if a.loss_norm == "token" else k * len(group)
                (l / norm).backward()
                gl += l.item()
            gn = torch.nn.utils.clip_grad_norm_(params, a.clip)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            rec = {"step": step, "epoch": ep, "loss": gl / n_tok, "lr": sched.get_last_lr()[0], "grad_norm": float(gn),
                   "seqs": len(group), "tokens": sum(len(e["input_ids"]) for e in group), "elapsed_s": time.time() - t0}
            if torch.cuda.is_available() and str(a.device).startswith("cuda"):
                rec["peak_GiB"] = torch.cuda.max_memory_allocated() / 2**30
            stats["step_losses"].append(rec["loss"])
            log.write(json.dumps(rec) + "\n")
            log.flush()
            if step % a.log_every == 0:
                print(json.dumps(rec), flush=True)
            if a.max_steps and step >= a.max_steps:
                break
        if held:
            stats["holdout_nll"].append(eval_nll(model, held, a.device))
            print(f"epoch {ep} holdout NLL: {stats['holdout_nll'][-1]:.4f}", flush=True)
        if a.save_every_epoch:
            print("saved", export_adapter(model, out / f"epoch{ep + 1}", a.rank, a.alpha, not a.no_dup_kv), flush=True)
        if a.max_steps and step >= a.max_steps:
            break
    info = export_adapter(model, out / "adapter", a.rank, a.alpha, not a.no_dup_kv)
    print("exported", info, flush=True)
    print("verified", verify_adapter(out / "adapter", Path(a.model)), flush=True)
    (out / "run_args.json").write_text(json.dumps({**vars(a), "stats": {k: v for k, v in stats.items() if k != "step_losses"}}, indent=1))
    return model, stats


def preflight(a) -> None:
    """One model load + fwd/bwd at --seq-len with random tokens (half the tokens trained): reports
    peak memory and tokens/s on the real hardware before committing to a full run."""
    dtype = torch.bfloat16
    t = time.time()
    model = load_text_model(Path(a.model), a.device, dtype, a.weights, a.attn,
                            a.layer_devices.split(",") if a.layer_devices else None)
    add_lora(model, a.targets.split(","), a.rank, a.alpha, 0.0)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.train()
    print(f"load {time.time() - t:.0f}s, mem {torch.cuda.memory_allocated() / 2**30:.1f} GiB", flush=True)
    for it in range(2):
        torch.cuda.synchronize()
        t = time.time()
        ids = torch.randint(1000, 200000, (a.seq_len,)).tolist()
        ex = {"input_ids": ids, "loss_mask": [0] * (a.seq_len // 2) + [1] * (a.seq_len - a.seq_len // 2)}
        l, k = masked_loss(model, ex, a.device)
        (l / k).backward()
        torch.cuda.synchronize()
        dt = time.time() - t
        print(f"iter {it}: seq={a.seq_len} {dt:.1f}s {a.seq_len / dt:.0f} tok/s "
              f"peak={torch.cuda.max_memory_allocated() / 2**30:.1f} GiB", flush=True)


# ----------------------------------------------------------------------------- tiny CPU self-test

def _write_tiny_checkpoint(d: Path, seed: int = 0) -> None:
    """Random 2-layer Gemma4 text model (sliding + k_eq_v global layer) saved in the same
    compressed-tensors layout/naming as the real checkpoint."""
    from compressed_tensors.compressors.pack_quantized.helpers import pack_to_int32
    from safetensors.torch import save_file
    from transformers.models.gemma4.modeling_gemma4 import Gemma4ForCausalLM
    from transformers.models.gemma4.configuration_gemma4 import Gemma4TextConfig

    real = json.loads((MODEL / "config.json").read_text())
    tcd = dict(real["text_config"])
    tcd.update(hidden_size=64, intermediate_size=128, num_hidden_layers=2, num_attention_heads=4,
               num_key_value_heads=2, num_global_key_value_heads=1, head_dim=16, global_head_dim=32,
               layer_types=["sliding_attention", "full_attention"], sliding_window=8, vocab_size=512,
               vocab_size_per_layer_input=512, max_position_embeddings=4096)
    torch.manual_seed(seed)
    m = Gemma4ForCausalLM(Gemma4TextConfig(**tcd)).float()
    with torch.no_grad():  # norms away from 1 / random so that bugs in loading show up
        for n, p in m.named_parameters():
            if "norm" in n:
                p.uniform_(0.5, 1.5)
            elif "embed_tokens" in n:  # default std 0.02 + frozen tied head caps |logits| ~1.5: unlearnable
                p.normal_(0.0, 0.5)
    gs = real["quantization_config"]["config_groups"]["group_0"]["weights"]["group_size"]
    sd = {}
    for n, t in m.state_dict().items():
        if n == "lm_head.weight":
            continue
        key = CKPT_PREFIX + n.removeprefix("model.")
        mod = n.rsplit(".", 1)[0]
        if n.endswith(".weight") and isinstance(m.get_submodule(mod), nn.Linear) and ".layers." in n:
            out_f, in_f = t.shape
            g = t.float().view(out_f, in_f // gs, gs)
            scale = (g.abs().amax(-1) / 7.5).clamp_min(1e-8).to(torch.bfloat16)
            q = torch.clamp(torch.round(g / scale.float().unsqueeze(-1)), -8, 7).to(torch.int8).view(out_f, in_f)
            base = key[: -len(".weight")]
            sd[base + ".weight_packed"] = pack_to_int32(q, 4)
            sd[base + ".weight_scale"] = scale
            sd[base + ".weight_shape"] = torch.tensor([out_f, in_f])
        else:
            sd[key] = t.to(torch.bfloat16).contiguous()
    sd["model.vision_tower.dummy.weight"] = torch.zeros(2)  # must be ignored by the loader
    d.mkdir(parents=True, exist_ok=True)
    save_file(sd, d / "model.safetensors")
    cfg = {"architectures": ["Gemma4ForConditionalGeneration"], "model_type": "gemma4",
           "quantization_config": real["quantization_config"], "text_config": tcd}
    (d / "config.json").write_text(json.dumps(cfg))


def _check_dequant_vs_reference(model_dir: Path, modules: list[str]) -> float:
    """Our vectorized dequant vs compressed-tensors' PackedQuantizationCompressor.decompress."""
    from compressed_tensors.compressors.pack_quantized.base import PackedQuantizationCompressor
    from compressed_tensors.quantization import QuantizationScheme
    from safetensors import safe_open
    qc = json.loads((model_dir / "config.json").read_text())["quantization_config"]
    g = qc["config_groups"]["group_0"]
    scheme = QuantizationScheme(targets=g["targets"], weights=g["weights"], format=g["format"])
    worst = 0.0
    with safe_open(_ckpt_files(model_dir)[0], "pt", device="cpu") as st:
        for mname in modules:
            k = CKPT_PREFIX + mname
            sd = {s: st.get_tensor(f"{k}.{s}") for s in ("weight_packed", "weight_scale", "weight_shape")}
            ref = PackedQuantizationCompressor.decompress(sd, scheme)["weight"]
            ours = dequant_int4(sd["weight_packed"], sd["weight_scale"], int(sd["weight_shape"][1]),
                                g["weights"]["group_size"])
            assert ours.dtype == ref.dtype and ours.shape == ref.shape, (mname, ours.dtype, ref.dtype)
            worst = max(worst, (ours.float() - ref.float()).abs().max().item())
    return worst


@torch.no_grad()
def _vllm_semantics_logits(model_dir: Path, adapter_dir: Path, ids: torch.Tensor, drop_v: bool) -> torch.Tensor:
    """Re-implements how vLLM applies the adapter: dense dequantized base; on k_eq_v layers the
    qkv_proj V slot holds a copy of the *base* k_proj weight and receives only the v_proj LoRA."""
    from safetensors.torch import load_file
    ref = load_text_model(model_dir, "cpu", torch.float32, "bf16", "sdpa")
    cfg = json.loads((adapter_dir / "adapter_config.json").read_text())
    s = cfg["lora_alpha"] / cfg["r"]
    for L in k_eq_v_layers(ref.config):
        attn = ref.model.layers[L].self_attn
        attn.v_proj = nn.Linear(attn.k_proj.in_features, attn.k_proj.out_features, bias=False)
        attn.v_proj.weight.data.copy_(attn.k_proj.weight.data)
    t = load_file(adapter_dir / "adapter_model.safetensors")
    for k in t:
        m = KEY_RE.match(k)
        if m.group(4) != "A" or (drop_v and m.group(3) == "v_proj"):
            continue
        mod = ref.get_submodule(f"model.layers.{m.group(1)}.{m.group(2)}.{m.group(3)}")
        B = t[k.replace("lora_A", "lora_B")].float()
        mod.weight.data += s * (B @ t[k].float())
    ref.eval()
    return ref(input_ids=ids[None]).logits[0]


def tiny_selftest(a) -> None:
    torch.set_num_threads(8)
    work = Path(tempfile.mkdtemp(prefix="tiny_lora_", dir=a.scratch or None))
    ck = work / "ckpt"
    _write_tiny_checkpoint(ck)
    tc, _ = text_config_of(ck)
    print(f"[tiny] checkpoint {ck}: layers={tc.layer_types} k_eq_v layers={sorted(k_eq_v_layers(tc))}")
    err = _check_dequant_vs_reference(ck, [f"layers.{L}.{p}" for L in range(2) for p in
                                           ("self_attn.q_proj", "self_attn.k_proj", "self_attn.o_proj", "mlp.down_proj")])
    print(f"[tiny] dequant vs compressed-tensors reference: max|diff|={err}")
    assert err == 0.0
    if a.check_real_dequant:
        err = _check_dequant_vs_reference(MODEL, ["layers.5.self_attn.k_proj", "layers.5.self_attn.o_proj",
                                                  "layers.0.self_attn.v_proj", "layers.0.mlp.down_proj"])
        print(f"[tiny] REAL checkpoint dequant vs reference (4 modules): max|diff|={err}")
        assert err == 0.0

    # toy data: 4 repos; answer span = 6 fixed tokens + copy of the first 6 context tokens (copy needs the global layer)
    rng = random.Random(0)
    data = work / "toy.jsonl"
    with open(data, "w") as f:
        for i, iid in enumerate(["fastapi_1", "fastapi_2", "rich_3", "mined_rich_ab12", "requests_4", "mined_fastapi_cd34"] * 2):
            ctx = [rng.randrange(10, 500) for _ in range(40)]
            ids = ctx + [5] + list(range(7, 13)) + ctx[:6] + [6]  # fixed format tokens + a copy span
            f.write(json.dumps({"run": "toy", "instance_id": iid, "segment": i, "input_ids": ids,
                                "loss_mask": [0] * 41 + [1] * 13}) + "\n")
    a2 = argparse.Namespace(**{**vars(a), "model": str(ck), "data": str(data), "out": str(work / "run"), "device": "cpu",
                               "dtype": a.tiny_dtype, "weights": "int4", "holdout_repo": "rich", "epochs": 30,
                               "grad_accum": 2, "lr": 1e-2, "rank": 8, "alpha": 16, "dropout": 0.0, "warmup": 0.05,
                               "max_steps": 0, "log_every": 30, "save_every_epoch": False, "layer_devices": None,
                               "targets": "q,k,v,o,gate,up,down", "max_tokens": 32768, "exclude_ids": None})
    model, st = train(a2)
    assert all(repo_of(i) != "rich" for i in st["train_ids"]) and st["holdout_ids"] == ["mined_rich_ab12", "rich_3"], st
    first, last = sum(st["step_losses"][:3]) / 3, sum(st["step_losses"][-3:]) / 3
    print(f"[tiny] LORO fold ok (train={st['train_ids']}, holdout={st['holdout_ids']}); "
          f"masked loss first3={first:.3f} last3={last:.3f}")
    assert last < 0.5 * first, "loss did not decrease"

    ad = work / "run" / "adapter"
    from safetensors.torch import load_file
    t = load_file(ad / "adapter_model.safetensors")
    for k in sorted(t):
        print(f"  {k} {tuple(t[k].shape)}")
    # vLLM-semantics equivalence (bf16-rounded LoRA weights copied back so only semantics differ)
    model.eval()
    with torch.no_grad():
        for mod in model.modules():
            if isinstance(mod, LoRALinear):
                mod.lora_A.data = mod.lora_A.data.to(torch.bfloat16).float()
                mod.lora_B.data = mod.lora_B.data.to(torch.bfloat16).float()
        ids = torch.tensor(json.loads(open(data).readline())["input_ids"])
        train_logits = model(input_ids=ids[None].to(torch.long)).logits[0].float()
        ok = (_vllm_semantics_logits(ck, ad, ids, drop_v=False) - train_logits).abs().max().item()
        bad = (_vllm_semantics_logits(ck, ad, ids, drop_v=True) - train_logits).abs().max().item()
    print(f"[tiny] max|logit diff| train-model vs vLLM-semantics: with v_proj copy={ok:.2e}  without={bad:.2e}")
    tol = 1e-3 if a.tiny_dtype == "fp32" else 1.0  # bf16 model vs fp32 reference, |logits| up to 30
    assert ok < tol and bad > 10 * max(ok, 1e-6), "k_eq_v export semantics check failed"
    print(f"[tiny] PASS  (artifacts in {work})")
    if not a.keep:
        shutil.rmtree(work)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data")
    ap.add_argument("--out", default="runs/lora")
    ap.add_argument("--model", default=str(MODEL))
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--layer-devices", default=None, help="e.g. cuda:0,cuda:1 (naive layer split; for --weights bf16)")
    ap.add_argument("--dtype", default="bf16", choices=["bf16", "fp32"])
    ap.add_argument("--weights", default="int4", choices=["int4", "bf16"])
    ap.add_argument("--attn", default="sdpa", help="sdpa | flex_attention | eager")
    ap.add_argument("--targets", default="q,k,v,o,gate,up,down")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=float, default=32)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--weight-decay", type=float, default=0.0)
    ap.add_argument("--warmup", type=float, default=0.05, help="fraction of steps")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--grad-accum", type=int, default=8, help="sequences per optimizer step")
    ap.add_argument("--loss-norm", default="token", choices=["token", "seq"])
    ap.add_argument("--clip", type=float, default=1.0)
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--holdout-repo", default=None, help="LORO: drop this repo (incl. its mined tasks) from training")
    ap.add_argument("--exclude-ids", default=None, help="file with instance_ids to drop")
    ap.add_argument("--no-grad-ckpt", dest="grad_ckpt", action="store_false")
    ap.add_argument("--no-dup-kv", action="store_true", help="do NOT copy k_proj LoRA to v_proj on k_eq_v layers")
    ap.add_argument("--save-every-epoch", action="store_true")
    ap.add_argument("--log-every", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--verify", default=None, help="only verify an existing adapter dir against --model")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--seq-len", type=int, default=32768)
    ap.add_argument("--tiny", action="store_true", help="CPU end-to-end self-test on a tiny random Gemma4")
    ap.add_argument("--tiny-dtype", default="fp32", choices=["fp32", "bf16"])
    ap.add_argument("--check-real-dequant", action="store_true", help="(tiny) also check 4 real modules (CPU, ~1 GB RAM)")
    ap.add_argument("--scratch", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.tiny:
        tiny_selftest(a)
    elif a.verify:
        print(verify_adapter(Path(a.verify), Path(a.model)))
    elif a.preflight:
        preflight(a)
    else:
        assert a.data, "--data required"
        train(a)


if __name__ == "__main__":
    main()

"""Local end-to-end evaluation that mirrors the Kaggle scorer (scripts/inference.py per HARNESS_README):
budgets from the submission's eval_config.yaml (scorer defaults otherwise), events compaction
(interval 5, overlap 2, threshold 14336, retention 5), context caching, submission limits, and our
subprocess-sandbox fixes (harness_patches). The `swegemma eval` CLI sets none of the compaction/cache
configs, which lets contexts grow unbounded.

Usage: .venv-eval/bin/python -m src.eval.run_eval --submission-dir DIR --results-dir OUT
         [--task-ids ID ...] [--concurrency N] [--api-base URL]
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import litellm
import yaml

import src.eval.harness_patches  # noqa: F401
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
from swegemma.config import EvalConfig, build_submission_limits
from swegemma.evaluate import Evaluator
from swegemma.models.registry import setup_gemma_model_registry

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SCORER_DEFAULTS = {"timeout_seconds": 300, "max_tool_calls": 100, "max_time_minutes": 60.0, "max_turns": None}


def load_budget(sub: Path) -> dict:
    cfg = dict(SCORER_DEFAULTS)
    f = sub / "eval_config.yaml"
    if f.exists():
        raw = yaml.safe_load(f.read_text()) or {}
        sec = raw.get("evaluation", raw)
        for k in cfg:
            if sec.get(k) is not None:
                cfg[k] = sec[k]
        if cfg["max_turns"] is None and sec.get("max_llm_calls") is not None:
            cfg["max_turns"] = sec["max_llm_calls"]
    return cfg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission-dir", required=True)
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--task-ids", nargs="*")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--api-base", default=os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8011/v1"))
    ap.add_argument("--display", default="quiet")
    a = ap.parse_args()

    litellm.drop_params = True
    sub = Path(a.submission_dir).resolve()
    budget = load_budget(sub)
    adapters = None
    try:
        from adk_submission import discover_adapters
        from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS

        adapters = discover_adapters(str(sub), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
    except Exception as e:  # noqa: BLE001
        print("adapter discovery failed:", e)
    models = setup_gemma_model_registry(api_base=a.api_base, api_key="EMPTY", adapter_manifest=adapters)
    limits, gen_constraints = build_submission_limits()
    cfg = EvalConfig(
        tasks_path=DATA / "tasks.jsonl",
        snapshots_dir=DATA / "snapshots",
        results_dir=Path(a.results_dir),
        submission_dir=sub,
        models=models,
        sandbox="subprocess",
        timeout_seconds=int(budget["timeout_seconds"]),
        max_time_minutes=float(budget["max_time_minutes"]),
        max_tool_calls=int(budget["max_tool_calls"]),
        max_turns=int(budget["max_turns"]) if budget["max_turns"] is not None else None,
        task_ids=a.task_ids or None,
        limits=limits,
        generation_constraints=gen_constraints,
        adapter_manifest=adapters,
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(
            compaction_interval=5, overlap_size=2, token_threshold=14336, event_retention_size=5
        ),
        graph_dir=str(DATA / "graphs"),
        embeddings_dir=str(DATA / "embeddings"),
        wheels_dir=DATA / "wheels",
        concurrency=a.concurrency,
        display_mode=a.display,
    )
    print(f"budget={budget} concurrency={a.concurrency} api={a.api_base}", flush=True)
    res = asyncio.run(Evaluator(cfg).run())
    print(f"Evaluation complete: {res.resolved}/{res.total} resolved ({res.resolution_rate:.2%})")


if __name__ == "__main__":
    main()

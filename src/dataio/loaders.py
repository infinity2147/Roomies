"""Loaders for the Kaggle competition data (tasks, graphs, embeddings, snapshots)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

# Graph / embedding / snapshot files are keyed by "<repo short name>_<base_commit>".
REPO_SHORT = {
    "fastapi/fastapi": "fastapi",
    "Textualize/rich": "rich",
    "psf/requests": "requests",
    "encode/httpx": "httpx",
}


@dataclass
class Task:
    instance_id: str
    repo: str
    base_commit: str
    patch: str
    test_patch: str
    problem_statement: str
    hints_text: str
    created_at: str

    @property
    def short(self) -> str:
        return REPO_SHORT.get(self.repo, self.repo.split("/")[-1])

    @property
    def key(self) -> str:
        return f"{self.short}_{self.base_commit}"


def load_tasks(path: Path = DATA / "tasks.jsonl") -> list[Task]:
    with open(path) as f:
        return [Task(**json.loads(line)) for line in f if line.strip()]


def graph_path(task: Task) -> Path:
    return DATA / "graphs" / f"{task.key}.json"


def embedding_path(task: Task) -> Path:
    return DATA / "embeddings" / f"{task.key}.npz"


def snapshot_candidates(task: Task) -> list[Path]:
    snap = DATA / "snapshots"
    return sorted(p for p in snap.glob(f"*{task.instance_id}*")) + sorted(
        p for p in snap.glob(f"*{task.base_commit}*")
    )


@lru_cache(maxsize=8)
def load_graph(key: str) -> dict:
    with open(DATA / "graphs" / f"{key}.json") as f:
        return json.load(f)


def load_embeddings(key: str) -> tuple[list[str], "np.ndarray"]:  # noqa: F821
    import numpy as np

    z = np.load(DATA / "embeddings" / f"{key}.npz")
    names = list(z.files)
    return names, np.stack([z[n] for n in names]).astype(np.float32)

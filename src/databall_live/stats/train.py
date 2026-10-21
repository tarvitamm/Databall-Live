"""Fit the pass-completion and xG models on a folder of simulated matches.

    uv run python -m databall_live.stats.train data/league
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from .onball import MODELS, fit_logistic, pass_features, predict, shot_features


def _collect(folder: str) -> tuple[list[list[float]], list[int], list[list[float]], list[int]]:
    from .kinematics import compute_kinematics
    from .match import load_match
    from .onball import pass_metrics, shot_metrics
    from .shape import compute_shape

    md = load_match(folder)
    kin, shape = compute_kinematics(md), compute_shape(md)
    passes, shots = pass_metrics(md, kin, shape), shot_metrics(md, kin)
    return ([pass_features(p) for p in passes], [int(p.complete) for p in passes],
            [shot_features(s) for s in shots], [int(s.outcome == "goal") for s in shots])


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    n_pos, n_neg = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / max(n_pos * n_neg, 1))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)
    folders = sorted(str(p) for p in args.root.iterdir() if (p / "tracking.jsonl").exists())
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        parts = list(pool.map(_collect, folders))
    MODELS.mkdir(exist_ok=True)
    for name, xi, yi, cols in (
        ("xpass", 0, 1, ["distance/20", "forward/20", "passer_space/5", "lane_defenders", "lofted"]),
        ("xg", 2, 3, ["distance/10", "angle", "header", "defenders_in_cone", "pressure/5"]),
    ):
        x = np.array([f for part in parts for f in part[xi]], dtype=float)
        y = np.array([v for part in parts for v in part[yi]], dtype=float)
        w = fit_logistic(x, y)
        p = np.array([predict(w, row) for row in x])
        (MODELS / f"{name}.json").write_text(json.dumps(
            {"features": cols, "weights": [round(float(v), 5) for v in w], "samples": int(len(y)),
             "base_rate": round(float(y.mean()), 4), "auc_train": round(_auc(y, p), 3)}, indent=2))
        print(f"{name}: {len(y)} samples, base rate {y.mean():.3f}, mean prediction {p.mean():.3f}, "
              f"train AUC {_auc(y, p):.3f}, weights {np.round(w, 3).tolist()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

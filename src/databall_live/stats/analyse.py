"""Run the stats engine over a stored match and write its patterns, metrics and match state.

    uv run databall-analyse data/league/m_0101 [--eval]
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ..contracts import Pattern
from .chains import shot_chains
from .defending import (
    PatternIds,
    between_lines_gaps,
    counter_presses,
    line_movements,
    overloads,
    recovery_runs,
    turnovers,
)
from .kinematics import Kinematics, compute_kinematics, physical_summary
from .match import MatchData, load_match
from .onball import PassMetrics, ShotMetrics, pass_metrics, score, shot_metrics
from .possession import Possession, compute_possession
from .pressing import PressWindow, detect_pressure_shifts, pressing_windows
from .runs import DetectedRun, detect_runs, measure_space, run_patterns
from .season import write_summary
from .shape import Shape, compute_shape
from .state import StateBin, control_and_chaos, momentum, momentum_swings
from .triggers import fatigue, triggers


@dataclass
class Analysis:
    md: MatchData
    kin: Kinematics
    poss: Possession
    shape: Shape
    runs: list[DetectedRun]
    press: list[PressWindow]
    passes: list[PassMetrics]
    shots: list[ShotMetrics]
    state: list[StateBin]
    momentum: np.ndarray
    patterns: list[Pattern]


def analyse(folder: str | Path) -> Analysis:
    md = load_match(folder)
    kin = compute_kinematics(md)
    poss = compute_possession(md)
    shape = compute_shape(md)

    runs = detect_runs(md, kin, poss, shape)
    for r in runs:
        if r.dragging:
            measure_space(md, kin, r)
    patterns = run_patterns(md, runs)
    patterns += detect_pressure_shifts(md, poss, shape, start_id=len(patterns) + 1)

    ids = PatternIds(len(patterns) + 1)
    lost = turnovers(md, poss)
    patterns += counter_presses(md, kin, poss, lost, ids)
    patterns += recovery_runs(md, kin, lost, ids)
    patterns += line_movements(md, poss, shape, ids)
    patterns += between_lines_gaps(md, poss, shape, ids)
    patterns += overloads(md, poss, ids)

    passes, shots = pass_metrics(md, kin, shape), shot_metrics(md, kin)
    score(passes, shots)
    patterns += triggers(md, kin, passes, shots, start_id=len(patterns) + 1)
    patterns += fatigue(md, kin, start_id=len(patterns) + 1)
    patterns += shot_chains(md, poss, shots, patterns, start_id=len(patterns) + 1)

    state = control_and_chaos(md, poss, passes)
    series = momentum(md, passes, shots)
    patterns += momentum_swings(md, series, patterns, start_id=len(patterns) + 1)
    patterns.sort(key=lambda p: (p.period, p.t_start))
    return Analysis(md=md, kin=kin, poss=poss, shape=shape, runs=runs, press=pressing_windows(md, poss, shape),
                    passes=passes, shots=shots, state=state, momentum=series, patterns=patterns)


def write(a: Analysis, folder: Path) -> None:
    with (folder / "patterns.jsonl").open("w") as f:
        for p in a.patterns:
            f.write(p.model_dump_json(exclude_none=True) + "\n")
    metrics = {
        "passes": [asdict(p) for p in a.passes],
        "shots": [asdict(s) for s in a.shots],
        "state": [asdict(s) for s in a.state],
        "press": [asdict(w) for w in a.press],
        "physical": physical_summary(a.md, a.kin),
        "momentum": a.momentum[:: 10].round(4).tolist(),
    }
    (folder / "metrics.json").write_text(json.dumps(metrics, default=float))
    write_summary(a, folder)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--eval", action="store_true", help="Grade against truth.json")
    args = ap.parse_args(argv)
    started = time.perf_counter()
    a = analyse(args.folder)
    write(a, args.folder)
    kinds: dict[str, int] = {}
    for p in a.patterns:
        kinds[p.type] = kinds.get(p.type, 0) + 1
    print(f"{a.md.meta.match}: {len(a.patterns)} patterns in {time.perf_counter() - started:.1f} s")
    print(json.dumps(dict(sorted(kinds.items()))))
    if args.eval:
        from .evaluate import load_truth, score_runs

        print("runs vs truth:", json.dumps(score_runs(a.md, a.runs, load_truth(args.folder)).__dict__))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

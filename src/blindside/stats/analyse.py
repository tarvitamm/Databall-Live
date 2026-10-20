"""Run the stats engine over a stored match and write its patterns.

    uv run blindside-analyse data/league/m_0101 [--eval]
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

from ..contracts import Pattern
from .kinematics import Kinematics, compute_kinematics, physical_summary
from .match import MatchData, load_match
from .possession import Possession, compute_possession
from .pressing import PressWindow, detect_pressure_shifts, pressing_windows
from .runs import DetectedRun, detect_runs, measure_space, run_patterns
from .shape import Shape, compute_shape


@dataclass
class Analysis:
    md: MatchData
    kin: Kinematics
    poss: Possession
    shape: Shape
    runs: list[DetectedRun]
    press: list[PressWindow]
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
    press = pressing_windows(md, poss, shape)
    patterns += detect_pressure_shifts(md, poss, shape, start_id=len(patterns) + 1)
    patterns.sort(key=lambda p: (p.period, p.t_start))
    return Analysis(md=md, kin=kin, poss=poss, shape=shape, runs=runs, press=press, patterns=patterns)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--eval", action="store_true", help="Grade against truth.json (evaluation only)")
    args = ap.parse_args(argv)
    started = time.perf_counter()
    a = analyse(args.folder)
    with (args.folder / "patterns.jsonl").open("w") as f:
        for p in a.patterns:
            f.write(p.model_dump_json(exclude_none=True) + "\n")
    kinds: dict[str, int] = {}
    for p in a.patterns:
        kinds[p.type] = kinds.get(p.type, 0) + 1
    print(f"{a.md.meta.match}: {len(a.patterns)} patterns {kinds} in {time.perf_counter() - started:.1f} s")
    phys = physical_summary(a.md, a.kin)
    top = sorted(phys.items(), key=lambda kv: -kv[1]["top_speed_kmh"])[:3]
    print("fastest:", [(pid, v["top_speed_kmh"]) for pid, v in top])
    if args.eval:
        from .evaluate import load_truth, score_runs

        print("runs vs truth:", json.dumps(score_runs(a.md, a.runs, load_truth(args.folder)).__dict__))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

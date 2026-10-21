"""Simulate many matches in parallel for training data, evaluation and the published dataset.

    uv run python -m databall_live.sim.batch --first-seed 100 --count 12 --out data/league
"""

from __future__ import annotations

import argparse
import itertools
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .clubs import CLUBS
from .tactics import SCENARIOS


def fixtures(first_seed: int, count: int, scenarios: list[str]) -> list[tuple[int, str, str, str]]:
    pairs = list(itertools.permutations(sorted(CLUBS), 2))
    out = []
    for k in range(count):
        home, away = pairs[k % len(pairs)]
        out.append((first_seed + k, home, away, scenarios[k % len(scenarios)]))
    return out


def _one(args: tuple[int, str, str, str, str, bool]) -> dict:
    from .boxscore import box_score
    from .cli import simulate

    seed, home, away, scenario, root, tracking = args
    match_id = f"m_{seed:04d}"
    engine = simulate(seed, home, away, scenario, Path(root) / match_id, tracking=tracking, match_id=match_id,
                      quiet=True)
    return {"match": match_id, "home": home, "away": away, "scenario": scenario, "box": box_score(engine)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--first-seed", type=int, default=100)
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--scenarios", default="free", help=f"comma-separated, from {', '.join(SCENARIOS)}")
    ap.add_argument("--out", type=Path, default=Path("data/league"))
    ap.add_argument("--no-tracking", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)
    scenarios = args.scenarios.split(",")
    jobs = [(s, h, a, sc, str(args.out), not args.no_tracking) for s, h, a, sc in
            fixtures(args.first_seed, args.count, scenarios)]
    args.out.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(_one, jobs))
    (args.out / "index.json").write_text(json.dumps(results, indent=2))
    for r in results:
        h, a = r["home"], r["away"]
        print(f"{r['match']} {h} {r['box'][h]['goals']}-{r['box'][a]['goals']} {a}  ({r['scenario']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

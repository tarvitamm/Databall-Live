"""Simulate one match and write events, tracking, metadata and hidden truth.

    uv run blindside-sim --seed 7 --home HAR --away RED --scenario the_press --out data/matches/m_0007
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from ..contracts import MatchMetadata, PlayerInfo, TeamInfo
from .boxscore import box_score, format_box_score
from .clubs import CLUBS, Club
from .engine import HZ, SIM_VERSION, MatchEngine
from .tactics import SCENARIOS

REFEREES = ["Alex Brannigan", "Jordan Pike", "Morgan Ellery", "Casey Wren"]
WEATHER = ["dry, 12 C", "light rain, 9 C", "overcast, 14 C", "windy, 10 C"]


def team_info(club: Club) -> TeamInfo:
    def info(p) -> PlayerInfo:
        return PlayerInfo(id=p.id, name=p.name, shirt=p.shirt, position=p.slot, foot=p.foot)

    return TeamInfo(code=club.code, name=club.name, colours=club.colours, formation=club.formation,
                    lineup=[info(p) for p in club.lineup], bench=[info(p) for p in club.bench])


def simulate(seed: int, home: str, away: str, scenario: str, out_dir: Path | None, tracking: bool = True,
             half_minutes: float = 45.0, match_id: str | None = None, quiet: bool = False) -> MatchEngine:
    engine = MatchEngine(CLUBS[home], CLUBS[away], seed=seed, scenario=scenario, match_id=match_id,
                         half_minutes=half_minutes)
    frames_file = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        if tracking:
            frames_file = (out_dir / "tracking.jsonl").open("w")

    def on_frame(frame: dict) -> None:
        if frames_file is not None:
            frames_file.write(json.dumps(frame, separators=(",", ":")) + "\n")

    started = time.perf_counter()
    truth = engine.run(on_event=lambda e: None, on_frame=on_frame)
    elapsed = time.perf_counter() - started
    if frames_file is not None:
        frames_file.close()

    if out_dir is not None:
        events = sorted(engine.events, key=lambda e: (e["period"], e["t"], int(e["id"][3:])))
        with (out_dir / "events.jsonl").open("w") as f:
            for e in events:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
        meta_rng = np.random.default_rng(seed + 1)
        meta = MatchMetadata(match=engine.match_id, seed=seed, scenario=scenario, sim_version=SIM_VERSION,
                             home=team_info(CLUBS[home]), away=team_info(CLUBS[away]), venue=CLUBS[home].venue,
                             kick_off="2026-10-24T15:00:00+01:00", weather=str(meta_rng.choice(WEATHER)),
                             referee=str(meta_rng.choice(REFEREES)), hz=HZ)
        (out_dir / "metadata.json").write_text(meta.model_dump_json(indent=2))
        (out_dir / "truth.json").write_text(truth.model_dump_json(indent=2))

    if not quiet:
        print(format_box_score(box_score(engine), home, away))
        print(f"simulated in {elapsed:.1f} s" + (f", written to {out_dir}" if out_dir else ""))
    return engine


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--home", default="HAR", choices=sorted(CLUBS))
    ap.add_argument("--away", default="RED", choices=sorted(CLUBS))
    ap.add_argument("--scenario", default="free", choices=SCENARIOS)
    ap.add_argument("--out", type=Path, default=None, help="Output folder; omit to only print the box score")
    ap.add_argument("--no-tracking", action="store_true", help="Skip writing tracking.jsonl")
    ap.add_argument("--half-minutes", type=float, default=45.0)
    ap.add_argument("--match-id", default=None, help="Defaults to m_<seed>")
    args = ap.parse_args(argv)
    if args.home == args.away:
        ap.error("home and away must differ")
    simulate(args.seed, args.home, args.away, args.scenario, args.out, tracking=not args.no_tracking,
             half_minutes=args.half_minutes, match_id=args.match_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())

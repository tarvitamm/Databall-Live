"""Grade the stats engine against the simulator's hidden truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..contracts import Pattern, Truth
from .match import MatchData
from .runs import DetectedRun


@dataclass
class RunScores:
    truth_runs: int
    detected_runs: int
    recall: float            # share of true runs we found
    precision: float         # share of our runs that match a true run
    follower_accuracy: float  # matched runs where we named the same follower (or none when he held)
    decoy_precision: float   # detected decoys whose true intent was decoy
    decoy_recall: float      # true decoy runs that a defender followed, which we flagged as decoys
    followed_truth: int
    matched: int
    exploited_decoy_recall: float = 0.0  # decoys a teammate actually attacked, that we flagged
    exploited_decoy_precision: float = 0.0  # our decoy flags that were decoys a teammate attacked


def load_truth(folder: str | Path) -> Truth:
    return Truth.model_validate_json((Path(folder) / "truth.json").read_text())


def score_runs(md: MatchData, runs: list[DetectedRun], truth: Truth) -> RunScores:
    def overlaps(r: DetectedRun, tr) -> bool:
        return (md.ids[r.player] == tr.player and r.period == tr.period
                and md.t[r.f0] <= tr.t_end + 0.5 and md.t[r.f1] >= tr.t_start - 0.5)

    matched_truth: set[str] = set()
    pairs: list[tuple[DetectedRun, object]] = []
    for r in runs:
        hit = next((tr for tr in truth.runs if overlaps(r, tr)), None)
        if hit is not None:
            pairs.append((r, hit))
            matched_truth.add(hit.id)
    follower_ok = sum(1 for r, tr in pairs
                      if (md.ids[r.follower] if r.follower is not None else None) == tr.followed_by)
    decoys = [(r, tr) for r, tr in pairs if r.decoy]
    true_decoy_followed = [(r, tr) for r, tr in pairs if tr.intent == "decoy" and tr.followed_by]
    exploited = {tr.linked_to for tr in truth.runs if tr.linked_to}
    true_exploited = [(r, tr) for r, tr in pairs if tr.id in exploited and tr.followed_by]
    return RunScores(
        exploited_decoy_recall=round(sum(1 for r, _ in true_exploited if r.decoy) / max(1, len(true_exploited)), 3),
        exploited_decoy_precision=round(sum(1 for _, tr in decoys if tr.id in exploited) / max(1, len(decoys)), 3),
        truth_runs=len(truth.runs),
        detected_runs=len(runs),
        recall=round(len(matched_truth) / max(1, len(truth.runs)), 3),
        precision=round(len(pairs) / max(1, len(runs)), 3),
        follower_accuracy=round(follower_ok / max(1, len(pairs)), 3),
        decoy_precision=round(sum(1 for _, tr in decoys if tr.intent == "decoy") / max(1, len(decoys)), 3),
        decoy_recall=round(sum(1 for r, _ in true_decoy_followed if r.decoy) / max(1, len(true_decoy_followed)), 3),
        followed_truth=sum(1 for tr in truth.runs if tr.followed_by),
        matched=len(pairs),
    )


def score_shifts(md: MatchData, shifts: list[Pattern], truth: Truth, window_s: float = 15 * 60) -> dict:
    """Did we flag each scripted tactical change, and how quickly? Flags not near a change are false alarms."""
    # only changes to pressing count
    changes, last = [], {}
    for c in truth.tactics:
        prev = last.get(c.team)
        last[c.team] = c
        if prev is None:
            continue
        delta = max(abs(c.tactics.press_intensity - prev.tactics.press_intensity),
                    abs(c.tactics.block_height - prev.tactics.block_height))
        if delta >= 0.15:
            changes.append(c)
    found, delays = 0, []
    used: set[str] = set()
    for c in changes:
        hits = [p for p in shifts if p.team == c.team and p.period == c.period and 0 <= p.t_start - c.t <= window_s]
        if hits:
            first = min(hits, key=lambda p: p.t_start)
            found += 1
            delays.append(first.t_start - c.t)
            used.update(p.id for p in hits)
    false_alarms = [p for p in shifts if p.id not in used]
    return {"changes": len(changes), "detected": found,
            "median_delay_min": round(sorted(delays)[len(delays) // 2] / 60.0, 1) if delays else None,
            "false_alarms": len(false_alarms)}


def _evaluate_one(folder: str) -> dict:
    from .analyse import analyse

    a = analyse(folder)
    truth = load_truth(folder)
    scores = score_runs(a.md, a.runs, truth).__dict__
    exploited = [tr for tr in truth.runs if tr.linked_to]
    scores["truth_decoys_exploited"] = len({tr.linked_to for tr in exploited})
    shifts = score_shifts(a.md, [p for p in a.patterns if p.type == "pressure_shift"], truth)
    scores["shift_detected"] = f"{shifts['detected']}/{shifts['changes']}"
    scores["shift_delay_min"] = shifts["median_delay_min"]
    scores["shift_false_alarms"] = shifts["false_alarms"]
    scores["match"] = a.md.meta.match
    scores["scenario"] = truth.scenario
    return scores


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from concurrent.futures import ProcessPoolExecutor

    ap = argparse.ArgumentParser(description="Grade the stats engine on every match in a folder")
    ap.add_argument("root", type=Path)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)
    folders = sorted(str(p) for p in args.root.iterdir() if (p / "truth.json").exists())
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_evaluate_one, folders))
    keys = ["recall", "precision", "follower_accuracy", "decoy_precision", "decoy_recall",
            "exploited_decoy_recall", "exploited_decoy_precision"]
    for r in rows:
        print(r["match"], r["scenario"].ljust(10), " ".join(f"{k}={r[k]:.2f}" for k in keys[:3]),
              f"| shifts {r['shift_detected']} delay {r['shift_delay_min']} min,",
              f"false alarms {r['shift_false_alarms']}")
    mean = {k: round(sum(r[k] for r in rows) / len(rows), 3) for k in keys}
    print("mean", json.dumps(mean))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

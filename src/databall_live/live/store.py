"""Load analysed matches for streaming, running the pipeline first when a match has not been analysed yet."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..stats.kinematics import Kinematics, compute_kinematics
from ..stats.match import MatchData, load_match


@dataclass
class Bundle:
    id: str
    folder: Path
    md: MatchData
    kin: Kinematics
    packets: list[dict]
    patterns: list[dict]
    metrics: dict
    goals: list[tuple[int, float, str, str]]          # period, t, team, scorer
    shots: list[tuple[int, float, str, float]]        # period, t, team, xg
    period_bounds: dict[int, tuple[float, float]] = field(default_factory=dict)

    def frame(self, period: int, t: float) -> int:
        return self.md.frame_at(period, t)

    def score(self, period: int, t: float) -> dict[str, int]:
        score = {code: 0 for code in self.md.codes}
        for p, gt, team, _ in self.goals:
            if p < period or (p == period and gt <= t):
                score[team] += 1
        return score

    def xg(self, period: int, t: float) -> dict[str, float]:
        total = {code: 0.0 for code in self.md.codes}
        for p, st, team, value in self.shots:
            if p < period or (p == period and st <= t):
                total[team] += value
        return {k: round(v, 2) for k, v in total.items()}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []


MAX_BUNDLES = 4


class MatchStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cache: dict[str, Bundle] = {}

    def ids(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if (p / "tracking.jsonl").exists())

    def summary(self, match_id: str) -> dict:
        folder = self.root / match_id
        meta = json.loads((folder / "metadata.json").read_text())
        goals = [e for e in _jsonl(folder / "events.jsonl") if e["type"] == "goal"]
        home, away = meta["home"]["code"], meta["away"]["code"]
        return {"id": match_id, "scenario": meta["scenario"], "venue": meta["venue"],
                "home": {"code": home, "name": meta["home"]["name"], "colours": meta["home"]["colours"]},
                "away": {"code": away, "name": meta["away"]["name"], "colours": meta["away"]["colours"]},
                "score": [sum(g["team"] == home for g in goals), sum(g["team"] == away for g in goals)],
                "analysed": (folder / "packets.jsonl").exists()}

    def get(self, match_id: str) -> Bundle:
        if match_id in self.cache:
            return self.cache[match_id]
        folder = self.root / match_id
        if not (folder / "packets.jsonl").exists():
            from ..insights.pipeline import run, save

            save(run(folder), folder)
        md = load_match(folder)
        metrics = json.loads((folder / "metrics.json").read_text())
        events = md.events
        goals = [(e["period"], e["t"], e["team"], e.get("player", "")) for e in events if e["type"] == "goal"]
        shot_events = {e["id"]: e for e in events if e["type"] == "shot"}
        shots = [(shot_events[s["event"]]["period"], shot_events[s["event"]]["t"], md.codes[s["team"]], s["xg"] or 0.0)
                 for s in metrics["shots"]]
        bounds = {p: (float(md.t[md.period == p][0]), float(md.t[md.period == p][-1])) for p in (1, 2)}
        packets = sorted(_jsonl(folder / "packets.jsonl"), key=lambda p: (p["period"], p["show_at"], p["priority"]))
        bundle = Bundle(id=match_id, folder=folder, md=md, kin=compute_kinematics(md), packets=packets,
                        patterns=_jsonl(folder / "patterns.jsonl"), metrics=metrics, goals=goals, shots=shots,
                        period_bounds=bounds)
        self.cache[match_id] = bundle
        while len(self.cache) > MAX_BUNDLES:
            self.cache.pop(next(iter(self.cache)))
        return bundle


def match_state(b: Bundle, period: int, t: float) -> dict:
    bins = [s for s in b.metrics["state"] if s["period"] < period or (s["period"] == period and s["t_end"] <= t)]
    last = bins[-1] if bins else None
    rows = [m for m in b.metrics["momentum"] if m[0] < period or (m[0] == period and m[1] <= t)]
    return {"label": last["label"] if last else "balanced", "chaos": last["chaos"] if last else 50,
            "control": last["control"] if last else [50, 50], "momentum": rows[-1][2] if rows else 0.0,
            "momentum_series": [r[2] for r in rows[-60:]]}


def state_message(b: Bundle, period: int, t: float) -> dict:
    return {"kind": "state", "period": period, "t": t, "score": b.score(period, t), "xg": b.xg(period, t),
            **match_state(b, period, t)}


def frame_message(b: Bundle, k: int) -> dict:
    md = b.md
    pos = np.round(md.pos[k], 2)
    return {"kind": "frame", "t": float(md.t[k]), "period": int(md.period[k]),
            "ball": [round(float(v), 2) for v in md.ball[k]],
            "players": {pid: [float(pos[i, 0]), float(pos[i, 1])] for i, pid in enumerate(md.ids)}}

"""The season so far: a compact summary of every match, and the current match compared with the ones before it.

Only matches that come before the current one count, so a live broadcast never knows the future.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import TYPE_CHECKING

import numpy as np

from .kinematics import physical_summary

if TYPE_CHECKING:
    from .analyse import Analysis

RUN_TYPES = ("run_in_behind", "checking_run", "overlap_run", "forward_run")
TEAM_METRICS = ("goals", "xg", "shots", "pressures_per_min", "ppda", "possession_pct", "decoy_runs", "runs",
                "counter_presses", "counter_press_wins", "high_regains_per_10")
PLAYER_METRICS = ("distance_km", "sprints", "top_speed_kmh", "decoy_runs", "dragged_m", "runs", "pressures", "passes",
                  "passes_complete", "shots", "xg", "goals", "recovery_runs")


def summarize(a: Analysis) -> dict:
    md = a.md
    home, away = md.codes
    goals = Counter(e["team"] for e in md.events if e["type"] == "goal")
    scorers = Counter(e.get("player") for e in md.events if e["type"] == "goal")
    xg_team: Counter = Counter()
    xg_player: Counter = Counter()
    shots_team: Counter = Counter()
    for s in a.shots:
        code = md.codes[s.team]
        xg_team[code] += s.xg or 0.0
        shots_team[code] += 1
        xg_player[md.ids[s.shooter]] += s.xg or 0.0
    by_team = {code: [p for p in a.patterns if p.team == code] for code in md.codes}
    teams = {}
    for k, code in enumerate(md.codes):
        windows = [w for w in a.press if w.team == k]
        state = [s.possession_share[k] for s in a.state]
        mine = by_team[code]
        presses = [p for p in mine if p.type == "counter_press"]
        regained = [p for p in presses if p.measures.get("regained") == "true"]
        teams[code] = {
            "goals": goals.get(code, 0),
            "xg": round(xg_team.get(code, 0.0), 2),
            "shots": shots_team.get(code, 0),
            "pressures_per_min": round(mean(w.pressures_per_min for w in windows), 1) if windows else 0.0,
            "ppda": round(mean(w.ppda for w in windows), 1) if windows else 0.0,
            "possession_pct": round(100 * mean(state)) if state else 50,
            "decoy_runs": sum(1 for p in mine if p.type == "decoy_run"),
            "runs": sum(1 for p in mine if p.type in RUN_TYPES),
            "counter_presses": len(presses),
            "counter_press_wins": len(regained),
            "high_regains_per_10": round(mean(w.high_regains_per_10 for w in windows), 1) if windows else 0.0,
        }
    physical = physical_summary(md, a.kin)
    players = {}
    for pid in md.ids:
        mine = [p for p in a.patterns if p.actor == pid]
        decoys = [p for p in mine if p.type == "decoy_run"]
        acts = [e for e in md.events if e.get("player") == pid]
        passes = [e for e in acts if e["type"] == "pass"]
        players[pid] = {
            "team": pid.split("_")[0],
            "distance_km": physical[pid]["distance_km"],
            "sprints": physical[pid]["sprints"],
            "top_speed_kmh": physical[pid]["top_speed_kmh"],
            "decoy_runs": len(decoys),
            "dragged_m": round(sum(float(p.measures.get("defender_displacement_m", 0)) for p in decoys), 1),
            "runs": sum(1 for p in mine if p.type in RUN_TYPES),
            "pressures": sum(1 for e in acts if e["type"] == "pressure"),
            "passes": len(passes),
            "passes_complete": sum(1 for e in passes if e.get("outcome") == "complete"),
            "shots": sum(1 for e in acts if e["type"] == "shot"),
            "xg": round(xg_player.get(pid, 0.0), 2),
            "goals": scorers.get(pid, 0),
            "recovery_runs": sum(1 for p in mine if p.type == "recovery_run"),
        }
    return {"match": md.meta.match, "home": home, "away": away,
            "score": {home: goals.get(home, 0), away: goals.get(away, 0)}, "teams": teams, "players": players}


def write_summary(a: Analysis, folder: Path) -> None:
    (folder / "summary.json").write_text(json.dumps(summarize(a), default=float))


def _result(summary: dict, code: str) -> str:
    other = summary["away"] if summary["home"] == code else summary["home"]
    mine, theirs = summary["score"][code], summary["score"][other]
    return "W" if mine > theirs else "D" if mine == theirs else "L"


class Season:
    def __init__(self, summaries: list[dict]) -> None:
        self.matches = sorted(summaries, key=lambda s: s["match"])

    @classmethod
    def load(cls, folder: Path) -> Season:
        """Every match summary that comes before this one, from its league and the earlier rounds."""
        folder = Path(folder)
        roots = [folder.parent, folder.parent.parent / "season"]
        found = {}
        for root in roots:
            for path in root.glob("*/summary.json"):
                if path.parent.name < folder.name:
                    found[path.parent.name] = json.loads(path.read_text())
        return cls(list(found.values()))

    def games(self, code: str) -> list[dict]:
        return [s for s in self.matches if code in (s["home"], s["away"])]

    def player_games(self, pid: str) -> list[dict]:
        return [s["players"][pid] for s in self.matches if pid in s["players"]]

    def team_avg(self, code: str, metric: str) -> float | None:
        values = [s["teams"][code][metric] for s in self.games(code)]
        return round(float(mean(values)), 2) if values else None

    def team_rank(self, code: str, metric: str, higher: bool = True) -> tuple[int, int] | None:
        clubs = {c for s in self.matches for c in s["teams"]}
        averages = {c: self.team_avg(c, metric) for c in clubs}
        averages = {c: v for c, v in averages.items() if v is not None}
        if code not in averages:
            return None
        order = sorted(averages, key=lambda c: -averages[c] if higher else averages[c])
        return order.index(code) + 1, len(order)

    def player_avg(self, pid: str, metric: str) -> float | None:
        values = [g[metric] for g in self.player_games(pid)]
        return round(float(mean(values)), 2) if values else None

    def player_best(self, pid: str, metric: str) -> float | None:
        values = [g[metric] for g in self.player_games(pid)]
        return max(values) if values else None

    def recent_best(self, pid: str, metric: str, n: int = 5) -> float | None:
        values = [g[metric] for g in self.player_games(pid)[-n:]]
        return max(values) if values else None

    def player_total(self, pid: str, metric: str) -> float:
        return sum(g[metric] for g in self.player_games(pid))

    def league_best(self, metric: str) -> tuple[float, str] | None:
        best = None
        for s in self.matches:
            for pid, g in s["players"].items():
                if best is None or g[metric] > best[0]:
                    best = (g[metric], pid)
        return best

    def leaders(self, metric: str, team: str | None = None) -> list[tuple[str, float]]:
        totals: Counter = Counter()
        for s in self.matches:
            for pid, g in s["players"].items():
                if team is None or g["team"] == team:
                    totals[pid] += g[metric]
        return [(pid, round(float(v), 2)) for pid, v in totals.most_common()]

    def total_rank(self, pid: str, metric: str, extra: float = 0.0) -> tuple[int, int] | None:
        """Where a player's season total, plus `extra` from today, ranks in the league."""
        totals = dict(self.leaders(metric))
        if not totals:
            return None
        mine = totals.get(pid, 0.0) + extra
        return 1 + sum(1 for p, v in totals.items() if p != pid and v > mine), len(totals)

    def form(self, code: str, n: int = 5) -> str:
        return "".join(_result(s, code) for s in self.games(code)[-n:])

    def last_meeting(self, a: str, b: str) -> dict | None:
        met = [s for s in self.matches if {s["home"], s["away"]} == {a, b}]
        return met[-1] if met else None

    def percentile(self, metric: str, value: float) -> int | None:
        values = np.array([g[metric] for s in self.matches for g in s["players"].values()], dtype=float)
        return int(round(100 * float((values < value).mean()))) if len(values) else None

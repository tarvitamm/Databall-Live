"""Read-only stats tools the analyst agents call.

Tools only see the match up to the moment being explained, and every value they return is logged, so the verifier
can check that an explanation cites nothing the agent did not actually see.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Annotated

from ..stats.analyse import Analysis
from ..stats.kinematics import count_sprints
from ..stats.season import PLAYER_METRICS, TEAM_METRICS, Season
from .storyteller import Names
from .text import minute

RUN_TYPES = ("run_in_behind", "checking_run", "overlap_run", "forward_run")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
SKIP_MEASURES = {"signals", "direction", "received", "exploited", "regained", "space_served"}


def _before(period: int, t: float, now: tuple[int, float]) -> bool:
    return period < now[0] or (period == now[0] and t <= now[1])


def _numbers(value: object, out: set[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        out.add(float(value))
    elif isinstance(value, str):
        out.update(float(x) for x in NUMBER.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            _numbers(v, out)
    elif isinstance(value, list | tuple):
        for v in value:
            _numbers(v, out)


class ToolLog:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record(self, name: str, args: dict, result: object) -> object:
        self.calls.append({"tool": name, "args": args, "result": result})
        return result

    def numbers(self) -> set[float]:
        out: set[float] = set()
        for call in self.calls:
            _numbers(call["result"], out)
        return out

    def text(self) -> str:
        return " ".join(str(call["result"]) for call in self.calls)

    def summary(self) -> list[str]:
        return [f"{c['tool']}({', '.join(f'{k}={v}' for k, v in c['args'].items() if v not in ('', None))})"
                for c in self.calls]


class MatchTools:
    def __init__(self, a: Analysis, names: Names, season: Season | None = None) -> None:
        self.a = a
        self.names = names
        self.season = season or Season([])
        self.events = {e["id"]: e for e in a.md.events}

    def _name(self, pid: str | None) -> str | None:
        return self.names.player.get(pid or "", pid)

    def _team(self, code: str | None) -> str | None:
        return self.names.team.get(code or "", code)

    def match_state(self, now: tuple[int, float]) -> dict:
        md = self.a.md
        goals = Counter(e["team"] for e in md.events if e["type"] == "goal" and _before(e["period"], e["t"], now))
        xg = Counter()
        for s in self.a.shots:
            e = self.events[s.event]
            if _before(e["period"], e["t"], now):
                xg[md.codes[s.team]] += s.xg or 0.0
        bins = [s for s in self.a.state if _before(s.period, s.t_end, now)]
        out: dict = {"minute": minute(now[1]),
                     "score": {self._team(c): goals.get(c, 0) for c in md.codes},
                     "xg": {self._team(c): round(xg.get(c, 0.0), 2) for c in md.codes}}
        if bins:
            s = bins[-1]
            out["last_5_minutes"] = {
                "label": s.label, "chaos_0_100": s.chaos,
                "control_0_100": {self._team(c): s.control[i] for i, c in enumerate(md.codes)},
                "possession_pct": {self._team(c): round(100 * s.possession_share[i]) for i, c in enumerate(md.codes)},
                "turnovers_per_min": s.turnovers_per_min,
                "passes_under_pressure_pct": round(100 * s.under_pressure_share)}
            out["recent_labels"] = [b.label for b in bins[-4:]]
        return out

    def pressing(self, team: str, now: tuple[int, float]) -> dict:
        md = self.a.md
        if team not in md.codes:
            return {"error": f"unknown club code {team}, use one of {list(md.codes)}"}
        k = md.team_index(team)
        windows = [w for w in self.a.press if w.team == k and _before(w.period, w.t_end, now)]
        if not windows:
            return {"team": self._team(team), "note": "not enough minutes played yet"}
        fields = ("pressures_per_min", "ppda", "line_height_m", "high_regains_per_10")
        latest = windows[-1]
        out = {"team": self._team(team), "window_minutes": latest.minutes,
               "latest": {f: round(getattr(latest, f), 1) for f in fields}}
        earlier = [w for w in windows if w.period == latest.period and latest.t_end - w.t_end >= 600]
        if earlier:
            out["ten_minutes_before"] = {f: round(getattr(earlier[-1], f), 1) for f in fields}
        return out

    def recent_patterns(self, now: tuple[int, float], kind: str = "", player: str = "", minutes: float = 10.0) -> list:
        lo = now[1] - 60.0 * minutes
        out = []
        for p in self.a.patterns:
            if p.period != now[0] or not (lo <= p.t_end <= now[1]):
                continue
            if kind and p.type != kind:
                continue
            if player and p.actor != player and player not in p.affected:
                continue
            measures = {k: v for k, v in p.measures.items() if k not in SKIP_MEASURES}
            out.append({"id": p.id, "type": p.type, "minute": minute(p.t_end), "player": self._name(p.actor),
                        "team": self._team(p.team), "affected": [self._name(x) for x in p.affected[:2]],
                        "measures": measures})
        return out[-8:]

    def player(self, player: str, now: tuple[int, float]) -> dict:
        md, kin = self.a.md, self.a.kin
        if player not in md.ids:
            return {"error": f"unknown player id {player}"}
        i = md.player_index(player)
        upto = md.frame_at(*now) + 1
        speed = kin.speed[:upto, i]
        mine = [p for p in self.a.patterns if p.actor == player and _before(p.period, p.t_end, now)]
        decoys = [p for p in mine if p.type == "decoy_run"]
        dragged = sum(float(p.measures.get("defender_displacement_m", 0)) for p in decoys)
        events = [e for e in md.events if e.get("player") == player and _before(e["period"], e["t"], now)]
        passes = [e for e in events if e["type"] == "pass"]
        return {"player": self._name(player), "position": md.positions[i],
                "distance_km": round(float(speed.sum() / md.hz / 1000.0), 2),
                "sprints": count_sprints(speed, md.hz), "top_speed_kmh": round(float(speed.max(initial=0.0)) * 3.6, 1),
                "runs": {k: sum(1 for p in mine if p.type == k) for k in RUN_TYPES},
                "decoy_runs": len(decoys),
                "defenders_dragged_m": round(dragged, 1),
                "pressures": sum(1 for e in events if e["type"] == "pressure"),
                "passes_complete": sum(1 for e in passes if e.get("outcome") == "complete"),
                "passes": len(passes), "shots": sum(1 for e in events if e["type"] == "shot")}

    def chain(self, pattern_id: str, now: tuple[int, float]) -> dict:
        by_id = {p.id: p for p in self.a.patterns}
        p = by_id.get(pattern_id)
        if p is None or p.type != "chain" or not _before(p.period, p.t_end, now):
            return {"error": f"no shot chain {pattern_id} yet"}
        links = []
        for q in (by_id[i] for i in p.evidence.patterns if i in by_id):
            links.append({"type": q.type, "player": self._name(q.actor),
                          "affected": [self._name(x) for x in q.affected],
                          "measures": {k: v for k, v in q.measures.items() if k not in SKIP_MEASURES}})
        return {"shooter": self._name(p.actor), "team": self._team(p.team), "minute": minute(p.t_end),
                "outcome": p.measures.get("outcome"), "xg": p.measures.get("xg"), "passes": p.measures.get("passes"),
                "seconds": p.measures.get("seconds"), "links": links}

    def season_record(self, team: str = "", player: str = "") -> dict:
        """Earlier matches this season: averages, bests and league ranks."""
        s = self.season
        if player:
            games = s.player_games(player)
            if not games:
                return {"player": self._name(player), "note": "no earlier matches this season"}
            return {"player": self._name(player), "games": len(games),
                    "average": {m: s.player_avg(player, m) for m in PLAYER_METRICS},
                    "best_in_a_game": {m: s.player_best(player, m) for m in PLAYER_METRICS},
                    "season_total": {m: round(s.player_total(player, m), 2) for m in ("decoy_runs", "goals", "shots")},
                    "league_rank_by_total": {m: (s.total_rank(player, m) or (None, None))[0]
                                             for m in ("decoy_runs", "goals")}}
        if team:
            if not s.games(team):
                return {"team": self._team(team), "note": "no earlier matches this season"}
            return {"team": self._team(team), "games": len(s.games(team)), "form_last_5": s.form(team),
                    "average": {m: s.team_avg(team, m) for m in TEAM_METRICS},
                    "league_rank_of_average": {m: (s.team_rank(team, m) or (None, None))[0]
                                               for m in ("pressures_per_min", "xg", "decoy_runs")}}
        return {"error": "give a club code or a player id"}

    def bind(self, now: tuple[int, float], log: ToolLog) -> list:
        """Agent Framework tools that see the match only up to `now` and log every answer."""
        from agent_framework import tool

        def match_state() -> dict:
            """Score, xG and who controls the game over the last five minutes."""
            return log.record("match_state", {}, self.match_state(now))

        def pressing(team: Annotated[str, "Club code, for example HAR"]) -> dict:
            """A club's pressing over the latest ten minutes and the ten minutes before."""
            return log.record("pressing", {"team": team}, self.pressing(team, now))

        def recent_patterns(kind: Annotated[str, "Pattern type to filter on, or empty for all"] = "",
                            player: Annotated[str, "Player id to filter on, or empty"] = "",
                            minutes: Annotated[float, "How many minutes to look back"] = 10.0) -> list:
            """Tactical patterns the detectors found recently: runs, decoys, presses, gaps, overloads, chains."""
            args = {"kind": kind, "player": player, "minutes": minutes}
            return log.record("recent_patterns", args, self.recent_patterns(now, kind, player, minutes))

        def player_summary(player: Annotated[str, "Player id, for example HAR_7"]) -> dict:
            """One player's running, off-ball and on-ball numbers so far."""
            return log.record("player_summary", {"player": player}, self.player(player, now))

        def shot_chain(pattern_id: Annotated[str, "Id of a chain pattern"]) -> dict:
            """The moves that led to a shot, link by link."""
            return log.record("shot_chain", {"pattern_id": pattern_id}, self.chain(pattern_id, now))

        def season_record(team: Annotated[str, "Club code, or empty"] = "",
                          player: Annotated[str, "Player id, or empty"] = "") -> dict:
            """This season before today: averages, best games, totals and league ranks for a club or a player."""
            args = {"team": team, "player": player}
            return log.record("season_record", args, self.season_record(team, player))

        return [tool(f) for f in (match_state, pressing, recent_patterns, player_summary, shot_chain, season_record)]

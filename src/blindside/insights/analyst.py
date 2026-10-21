"""Turn detected patterns and match state into insights: a claim, its signals, evidence and the facts to tell it."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..contracts import Evidence, Insight, ModelInfo, Pattern
from ..stats.analyse import Analysis
from ..stats.kinematics import count_sprints
from ..stats.season import Season
from ..stats.state import StateBin

PROMPT_VERSION = "templates-v1"
TACTICAL = {"pressure_shift", "momentum_swing", "counter_press", "between_lines_gap", "overload"}
PLAYER = {"decoy_run", "chain", "fatigue", "speed_tag", "match_top_speed"}
MIN_GAP_S = 45.0
REPEAT_GAP_S = {"decoy_run": 600.0, "overload": 600.0, "between_lines_gap": 300.0, "counter_press": 300.0,
                "match_state": 600.0, "record": 240.0, "standout": 30.0}
MIN_GAMES = 3
RECENT_GAMES = 5
STANDOUT_RATIO = 1.35
STANDOUT_MIN_AVG = {"decoy_runs": 3.0, "sprints": 12.0, "pressures": 15.0, "distance_km": 8.0}
PREVIEW_AT_S = 20.0


@dataclass
class Draft:
    insight: Insight
    key: str
    facts: dict = field(default_factory=dict)
    seen: set[float] = field(default_factory=set)
    seen_text: str = ""
    tools: list[str] = field(default_factory=list)


class Builder:
    def __init__(self, a: Analysis, agent: str, season: Season | None = None) -> None:
        self.a = a
        self.agent = agent
        self.season = season or Season([])
        self.drafts: list[Draft] = []
        self.speed_records: dict[str, float] = {}
        self.decoy_records: dict[str, int] = {}

    def add(self, kind: str, key: str, t: float, period: int, facts: dict, signals: dict, entities: dict,
            confidence: float, significance: float, evidence: Evidence) -> None:
        insight = Insight(id="", match=self.a.md.meta.match, t=round(t, 1), period=period, type=kind, claim="",
                          signals=signals, mechanism="", consequence="", evidence=evidence, entities=entities,
                          confidence=round(min(confidence, 0.95), 2), significance=round(significance, 2),
                          model=ModelInfo(analyst=self.agent, prompt_version=PROMPT_VERSION))
        self.drafts.append(Draft(insight, key, facts))

    def opp(self, code: str) -> str:
        home, away = self.a.md.codes
        return away if code == home else home

    def take(self) -> list[Draft]:
        out, self.drafts = self.drafts, []
        return out


def _press_leaders(a: Analysis, team: str, t: float, period: int, k: int = 2) -> list[tuple[str, int]]:
    counts = Counter(e["player"] for e in a.md.events if e["type"] == "pressure" and e.get("team") == team
                     and e["period"] == period and t - 600 <= e["t"] <= t)
    return counts.most_common(k)


def _evidence(p: Pattern, extra_events: list[str] | None = None) -> Evidence:
    return Evidence(events=extra_events or [], patterns=[p.id] + p.evidence.patterns, window=p.evidence.window)


def draft_tactical(b: Builder, p: Pattern, by_id: dict[str, Pattern]) -> None:
    team = p.team or ""
    m = p.measures
    if p.type == "pressure_shift":
        leaders = _press_leaders(b.a, team, p.t_end, p.period)
        facts = {"team": team, "opp": b.opp(team), "pb": m["pressures_per_min_before"],
                 "pa": m["pressures_per_min_after"], "lb": m["line_height_m_before"], "la": m["line_height_m_after"],
                 "leaders": [pid for pid, _ in leaders]}
        if leaders:
            facts.update(focus=leaders[0][0], fn=leaders[0][1])
        signals = {k: [m[f"{k}_before"], m[f"{k}_after"]]
                   for k in ("pressures_per_min", "line_height_m", "ppda", "high_regains_per_10")}
        agreeing = len(str(m["signals"]).split(","))
        key = "pressure_harder" if m["direction"] == "harder" else "pressure_softer"
        usual = b.season.team_avg(team, "pressures_per_min")
        if key == "pressure_harder" and usual and len(b.season.games(team)) >= MIN_GAMES and facts["pa"] > usual * 1.1:
            facts["sa"] = usual
            key = "pressure_harder_season"
        b.add("pressure_shift", key, p.t_end, p.period, facts, signals,
              {"teams": [team, facts["opp"]], "players": facts["leaders"]}, 0.55 + 0.1 * agreeing, p.significance,
              _evidence(p))
    elif p.type == "momentum_swing":
        drivers = list(dict.fromkeys(by_id[i].type for i in p.evidence.patterns if i in by_id))[:3]
        b.add("momentum_swing", "momentum_swing", p.t_start, p.period,
              {"team": team, "opp": b.opp(team), "drivers": drivers}, {"balance": float(m["balance"])},
              {"teams": [team]}, 0.65, p.significance, _evidence(p))
    elif p.type == "counter_press" and m.get("regained") == "true" and int(m["pressers"]) >= 3:
        b.add("counter_press", "counter_press", p.t_end, p.period,
              {"team": team, "opp": b.opp(team), "n": m["pressers"], "s": m["seconds_to_regain"]},
              {"pressers": float(m["pressers"])}, {"teams": [team]}, 0.8, p.significance, _evidence(p))
    elif p.type == "between_lines_gap" and m.get("exploited") == "true" and p.affected:
        b.add("between_lines_gap", "gap_exploited", p.t_end, p.period,
              {"team": team, "opp": b.opp(team), "gap": m["max_gap_m"], "player": p.affected[0]},
              {"max_gap_m": m["max_gap_m"]}, {"teams": [team, b.opp(team)], "players": [p.affected[0]]}, 0.75,
              p.significance, _evidence(p))
    elif p.type == "overload":
        b.add("overload", "overload", p.t_end, p.period,
              {"team": team, "a": m["attackers"], "d": m["defenders"], "side": m["side"]},
              {"attackers": float(m["attackers"]), "defenders": float(m["defenders"])}, {"teams": [team]}, 0.7,
              p.significance, _evidence(p))


def draft_player(b: Builder, p: Pattern, by_id: dict[str, Pattern]) -> None:
    team = p.team or ""
    m = p.measures
    if p.type == "decoy_run":
        served = m.get("space_served") == "true"
        if not p.affected or "beneficiary" not in m or not (served or p.significance >= 0.6):
            return
        md = b.a.md
        defender = p.affected[0]
        gain = float(m.get("space_value_gain", 0.0))
        facts = {"team": team, "opp": b.opp(team), "runner": p.actor, "defender": defender,
                 "pos": md.positions[md.player_index(defender)], "d": m["defender_displacement_m"],
                 "benef": m["beneficiary"], "served": served}
        signals = {"defender_displacement_m": m["defender_displacement_m"], "space_value_gain": gain}
        confidence = 0.6 + (0.2 if served else 0.0) + (0.1 if gain >= 0.15 else 0.0)
        today = _decoys_so_far(b.a, p)
        key = "decoy_run"
        if len(b.season.player_games(p.actor)) >= MIN_GAMES:
            facts["sd"] = int(b.season.player_total(p.actor, "decoy_runs")) + today
            rank = b.season.total_rank(p.actor, "decoy_runs", extra=today)
            facts["lead"] = bool(rank and rank[0] == 1)
            key = "decoy_run_season"
        b.add("decoy_run", key, p.t_end + 1.0, p.period, facts, signals,
              {"teams": [team], "players": [p.actor, defender, facts["benef"]]}, confidence, p.significance,
              _evidence(p))
        draft_decoy_record(b, p, today)
    elif p.type == "chain":
        xg = float(m["xg"])
        goal = m["outcome"] == "goal"
        linked = [by_id[i] for i in p.evidence.patterns if i in by_id]
        decoys = [q for q in linked if q.type == "decoy_run" and q.affected]
        if not goal and xg < 0.15 and not decoys:
            return
        facts = {"team": team, "opp": b.opp(team), "outcome": m["outcome"], "shooter": p.actor, "xg": xg,
                 "passes": m["passes"], "sec": m["seconds"]}
        players = [p.actor]
        key = "chain" if int(m["passes"]) > 0 else "chain_solo"
        if decoys:
            facts.update(decoy=decoys[0].actor, defender=decoys[0].affected[0])
            players += [decoys[0].actor, decoys[0].affected[0]]
            key = "chain_decoy"
        signals = {"xg": xg, "passes": float(m["passes"]), "seconds": float(m["seconds"])}
        if goal:
            scored = [e["team"] for e in b.a.md.events if e["type"] == "goal"
                      and (e["period"], e["t"]) <= (p.period, p.t_end + 1.0)]
            gf, ga = scored.count(team), scored.count(b.opp(team))
            state = "ahead" if gf - 1 == ga else "extends" if gf - 1 > ga else "level" if gf == ga else "back"
            facts.update(gf=gf, ga=ga, state=state)
        if goal and b.season.player_games(p.actor):
            facts["sg"] = int(b.season.player_total(p.actor, "goals")) + _goals_so_far(b.a, p)
            facts["focus"] = p.actor
            key = "goal_decoy" if decoys else "goal" if int(m["passes"]) > 0 else "goal_solo"
        b.add("chain", key, p.t_end + 1.0, p.period, facts, signals, {"teams": [team], "players": players}, 0.9,
              max(p.significance, 0.9 if goal else 0.0), _evidence(p, p.evidence.events))
    elif p.type in ("speed_tag", "match_top_speed"):
        draft_speed_record(b, p)
    elif p.type == "fatigue":
        facts = {"team": team, "player": p.actor, "pct": m["high_intensity_share_change_pct"],
                 "now": m["top_speed_kmh_now"], "early": m["top_speed_kmh_early"], "focus": p.actor}
        b.add("fatigue", "fatigue", p.t_end, p.period, facts, {"top_speed_kmh": [facts["early"], facts["now"]]},
              {"teams": [team], "players": [p.actor]}, 0.7, p.significance, _evidence(p))


def _decoys_so_far(a: Analysis, p: Pattern) -> int:
    return sum(1 for q in a.patterns if q.type == "decoy_run" and q.actor == p.actor
               and (q.period, q.t_end) <= (p.period, p.t_end))


def _goals_so_far(a: Analysis, p: Pattern) -> int:
    return sum(1 for e in a.md.events if e["type"] == "goal" and e.get("player") == p.actor
               and (e["period"], e["t"]) <= (p.period, p.t_end + 1.0))


def draft_speed_record(b: Builder, p: Pattern) -> None:
    """A sprint faster than the player has managed all season, or faster than anyone in the league."""
    pid = p.actor or ""
    v = float(p.measures["speed_kmh"])
    best = b.season.player_best(pid, "top_speed_kmh")
    recent = b.season.recent_best(pid, "top_speed_kmh", RECENT_GAMES)
    if best is None or recent is None or len(b.season.player_games(pid)) < MIN_GAMES:
        return
    if v <= recent or v <= b.speed_records.get(pid, 0.0):
        return
    b.speed_records[pid] = v
    league = b.season.league_best("top_speed_kmh")
    facts = {"team": p.team, "player": pid, "focus": pid, "v": v, "pv": best}
    key = "record_speed"
    if league and v > league[0]:
        facts["lg"] = league[0]
        key = "record_speed_league"
    elif v <= best:
        facts.update(pv=recent, n=RECENT_GAMES)
        key = "record_speed_recent"
    b.add("record", key, p.t_end + 1.0, p.period, facts, {"speed_kmh": [facts["pv"], v]},
          {"teams": [p.team or ""], "players": [pid]}, 0.95, 0.75 if key == "record_speed_league" else 0.6,
          _evidence(p))


def draft_decoy_record(b: Builder, p: Pattern, today: int) -> None:
    """More decoy runs in this match than the player has made in any game this season."""
    pid = p.actor or ""
    best = b.season.player_best(pid, "decoy_runs")
    if best is None or len(b.season.player_games(pid)) < MIN_GAMES or best < 2 or today <= best:
        return
    if today <= b.decoy_records.get(pid, 0):
        return
    b.decoy_records[pid] = today
    b.add("record", "record_decoys", p.t_end + 2.0, p.period,
          {"team": p.team, "runner": pid, "focus": pid, "n": today, "pd": int(best)},
          {"decoy_runs": [float(best), float(today)]}, {"teams": [p.team or ""], "players": [pid]}, 0.9, 0.65,
          _evidence(p))


def _so_far(a: Analysis, pid: str, period: int, t: float) -> dict[str, float]:
    md = a.md
    i = md.player_index(pid)
    upto = md.frame_at(period, t) + 1
    speed = a.kin.speed[:upto, i]
    done = lambda p, et: p < period or (p == period and et <= t)  # noqa: E731
    return {"decoy_runs": sum(1 for q in a.patterns if q.type == "decoy_run" and q.actor == pid
                              and done(q.period, q.t_end)),
            "sprints": count_sprints(speed, md.hz),
            "pressures": sum(1 for e in md.events if e["type"] == "pressure" and e.get("player") == pid
                             and done(e["period"], e["t"])),
            "distance_km": round(float(speed.sum() / md.hz / 1000.0), 1)}


def draft_standouts(b: Builder, period: int, t: float, k: int = 2) -> None:
    """At half-time: the players running well above their usual season pace."""
    md = b.a.md
    start1, end1 = float(md.t[md.period == 1][0]), float(md.t[md.period == 1][-1])
    played = (t - start1) if period == 1 else (end1 - start1) + (t - float(md.t[md.period == 2][0]))
    pace = max(played / 5400.0, 0.2)
    found = []
    for pid in md.ids:
        if len(b.season.player_games(pid)) < MIN_GAMES:
            continue
        now = _so_far(b.a, pid, period, t)
        for metric, least in STANDOUT_MIN_AVG.items():
            avg = b.season.player_avg(pid, metric)
            if not avg or avg < least:
                continue
            ratio = now[metric] / (avg * pace)
            if ratio >= (STANDOUT_RATIO if metric != "distance_km" else 1.08):
                found.append((ratio, pid, metric, now[metric], avg))
    seen: set[str] = set()
    for ratio, pid, metric, value, avg in sorted(found, reverse=True):
        if pid in seen or len(seen) >= k:
            continue
        seen.add(pid)
        team = pid.split("_")[0]
        facts = {"team": team, "player": pid, "focus": pid, "metric": metric, "avg": round(avg, 1)}
        if metric == "distance_km":
            facts["now"] = value
            key = "standout_distance"
        else:
            facts["cnt"] = int(value)
            key = "standout"
        b.add("standout", key, t + 3.0, period, facts, {metric: [round(avg * pace, 1), float(value)]},
              {"teams": [team], "players": [pid]}, 0.85, min(0.5 + 0.1 * ratio, 0.8), Evidence(window=(t - 600.0, t)))


def draft_preview(b: Builder) -> None:
    """The story before kick-off: last meeting, form and the off-ball specialist to watch."""
    s = b.season
    home, away = b.a.md.codes
    if len(s.games(home)) < MIN_GAMES or len(s.games(away)) < MIN_GAMES:
        return
    form_home, form_away = s.form(home), s.form(away)
    facts: dict = {"team": home, "opp": away, "hw": form_home.count("W"), "aw": form_away.count("W"),
                   "n": min(len(form_home), len(form_away))}
    squads = set(b.a.md.ids)
    leaders = [(pid, v) for pid, v in s.leaders("decoy_runs") if pid in squads]
    players = []
    if leaders:
        star, total = leaders[0]
        rank = s.total_rank(star, "decoy_runs")
        facts.update(star=star, focus=star, sd=int(total), lead=bool(rank and rank[0] == 1))
        players = [star]
    met = s.last_meeting(home, away)
    key = "preview"
    if met:
        facts.update(lh=met["score"][home], la=met["score"][away])
        key = "preview_h2h"
    b.add("preview", key, PREVIEW_AT_S, 1, facts, {"form_wins": [float(facts["hw"]), float(facts["aw"])]},
          {"teams": [home, away], "players": players}, 0.95, 0.7, Evidence(window=(0.0, PREVIEW_AT_S)))


def draft_state(b: Builder, bins: list[StateBin], previous: str | None) -> str | None:
    """Insights for changes in who controls the game. Returns the last label seen."""
    for s in bins:
        if s.label != previous and s.label != "balanced":
            evidence = Evidence(window=(s.t_end - 300.0, s.t_end))
            signals = {"chaos": s.chaos, "control": list(s.control)}
            if s.label == "chaotic":
                facts = {"tpm": s.turnovers_per_min, "under": round(100 * s.under_pressure_share)}
                b.add("match_state", "chaotic", s.t_end, s.period, facts, signals, {"teams": list(b.a.md.codes)},
                      0.7, 0.5, evidence)
            else:
                team = s.label.split()[0]
                k = b.a.md.team_index(team)
                facts = {"team": team, "opp": b.a.md.codes[1 - k], "ca": s.control[k], "cb": s.control[1 - k],
                         "poss": round(100 * s.possession_share[k]), "terr": round(100 * s.territory[k])}
                b.add("match_state", "in_control", s.t_end, s.period, facts, signals, {"teams": [team]}, 0.7, 0.45,
                      evidence)
        previous = s.label
    return previous


class RepeatGuard:
    """Keeps the feed readable: no repeats of the same story too soon, no two stories about one team at once."""

    def __init__(self) -> None:
        self.last_kind: dict[str, float] = {}
        self.last_team: dict[str, tuple[float, float]] = {}

    @staticmethod
    def _abs(d: Draft) -> float:
        return d.insight.t + (10_000.0 if d.insight.period == 2 else 0.0)

    def allow(self, d: Draft, commit: bool = True) -> bool:
        now = self._abs(d)
        team = (d.insight.entities.get("teams") or [""])[0]
        goal = d.facts.get("outcome") == "goal"
        gap = REPEAT_GAP_S.get(d.insight.type)
        kind_key = f"{d.insight.type}:{d.facts.get('runner') or d.facts.get('player') or team}"
        if gap is not None and now - self.last_kind.get(kind_key, -1e9) < gap and not goal:
            return False
        last_t, last_sig = self.last_team.get(team, (-1e9, 0.0))
        if now - last_t < MIN_GAP_S and not goal and d.insight.significance < last_sig + 0.2:
            return False
        if not commit:
            return True
        if gap is not None:
            self.last_kind[kind_key] = now
        self.last_team[team] = (now, d.insight.significance)
        return True

    def save(self) -> dict:
        return {"kind": self.last_kind, "team": {k: list(v) for k, v in self.last_team.items()}}

    def restore(self, state: dict) -> None:
        self.last_kind = dict(state.get("kind", {}))
        self.last_team = {k: (v[0], v[1]) for k, v in state.get("team", {}).items()}

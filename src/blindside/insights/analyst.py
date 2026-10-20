"""Turn detected patterns and match state into insights: a claim, its signals, evidence and the facts to tell it."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..contracts import Evidence, Insight, ModelInfo, Pattern
from ..stats.analyse import Analysis
from ..stats.state import StateBin

PROMPT_VERSION = "templates-v1"
TACTICAL = {"pressure_shift", "momentum_swing", "counter_press", "between_lines_gap", "overload"}
PLAYER = {"decoy_run", "chain", "fatigue"}
MIN_GAP_S = 45.0
REPEAT_GAP_S = {"decoy_run": 600.0, "overload": 600.0, "between_lines_gap": 300.0, "counter_press": 300.0,
                "match_state": 600.0}


@dataclass
class Draft:
    insight: Insight
    key: str
    facts: dict = field(default_factory=dict)
    seen: set[float] = field(default_factory=set)
    seen_text: str = ""
    tools: list[str] = field(default_factory=list)


class Builder:
    def __init__(self, a: Analysis, agent: str) -> None:
        self.a = a
        self.agent = agent
        self.drafts: list[Draft] = []

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
        b.add("decoy_run", "decoy_run", p.t_end + 1.0, p.period, facts, signals,
              {"teams": [team], "players": [p.actor, defender, facts["benef"]]}, confidence, p.significance,
              _evidence(p))
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
        b.add("chain", key, p.t_end + 1.0, p.period, facts, signals, {"teams": [team], "players": players}, 0.9,
              max(p.significance, 0.9 if goal else 0.0), _evidence(p, p.evidence.events))
    elif p.type == "fatigue":
        facts = {"team": team, "player": p.actor, "pct": m["high_intensity_share_change_pct"],
                 "now": m["top_speed_kmh_now"], "early": m["top_speed_kmh_early"], "focus": p.actor}
        b.add("fatigue", "fatigue", p.t_end, p.period, facts, {"top_speed_kmh": [facts["early"], facts["now"]]},
              {"teams": [team], "players": [p.actor]}, 0.7, p.significance, _evidence(p))


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
        kind_key = f"{d.insight.type}:{d.facts.get('runner') or team}"
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

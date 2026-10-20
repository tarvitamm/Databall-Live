"""Turn detected patterns and match state into insights: a claim, its signals, evidence and the facts to tell it."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..contracts import Evidence, Insight, ModelInfo, Pattern
from ..stats.analyse import Analysis

ANALYST = "template-analyst"
PROMPT_VERSION = "templates-v1"
MIN_GAP_S = 45.0
REPEAT_GAP_S = {"decoy_run": 600.0, "overload": 600.0, "between_lines_gap": 300.0, "counter_press": 300.0}


@dataclass
class Draft:
    insight: Insight
    key: str
    facts: dict = field(default_factory=dict)


class Builder:
    def __init__(self, a: Analysis) -> None:
        self.a = a
        self.drafts: list[Draft] = []

    def add(self, kind: str, key: str, t: float, period: int, facts: dict, signals: dict, entities: dict,
            confidence: float, significance: float, evidence: Evidence) -> None:
        insight = Insight(id=f"in_{len(self.drafts) + 1}", match=self.a.md.meta.match, t=round(t, 1), period=period,
                          type=kind, claim="", signals=signals, mechanism="", consequence="", evidence=evidence,
                          entities=entities, confidence=round(min(confidence, 0.95), 2),
                          significance=round(significance, 2),
                          model=ModelInfo(analyst=ANALYST, prompt_version=PROMPT_VERSION))
        self.drafts.append(Draft(insight, key, facts))

    def opp(self, code: str) -> str:
        home, away = self.a.md.codes
        return away if code == home else home


def _press_leaders(a: Analysis, team: str, t: float, period: int, k: int = 2) -> list[tuple[str, int]]:
    counts = Counter(e["player"] for e in a.md.events if e["type"] == "pressure" and e.get("team") == team
                     and e["period"] == period and t - 600 <= e["t"] <= t)
    return counts.most_common(k)


def _evidence(p: Pattern, extra_events: list[str] | None = None) -> Evidence:
    return Evidence(events=extra_events or [], patterns=[p.id] + p.evidence.patterns, window=p.evidence.window)


def _pressure_shift(b: Builder, p: Pattern) -> None:
    team = p.team or ""
    leaders = _press_leaders(b.a, team, p.t_end, p.period)
    facts = {"team": team, "opp": b.opp(team), "pb": p.measures["pressures_per_min_before"],
             "pa": p.measures["pressures_per_min_after"], "lb": p.measures["line_height_m_before"],
             "la": p.measures["line_height_m_after"], "leaders": [pid for pid, _ in leaders]}
    if leaders:
        facts.update(focus=leaders[0][0], fn=leaders[0][1])
    signals = {k: [p.measures[f"{k}_before"], p.measures[f"{k}_after"]]
               for k in ("pressures_per_min", "line_height_m", "ppda", "high_regains_per_10")}
    agreeing = len(str(p.measures["signals"]).split(","))
    key = "pressure_harder" if p.measures["direction"] == "harder" else "pressure_softer"
    b.add("pressure_shift", key, p.t_end, p.period, facts, signals,
          {"teams": [team, facts["opp"]], "players": facts["leaders"]}, 0.55 + 0.1 * agreeing, p.significance,
          _evidence(p))


def _decoy(b: Builder, p: Pattern) -> None:
    served = p.measures.get("space_served") == "true"
    if not p.affected or "beneficiary" not in p.measures or not (served or p.significance >= 0.6):
        return
    team, defender = p.team or "", p.affected[0]
    md = b.a.md
    gain = float(p.measures.get("space_value_gain", 0.0))
    facts = {"team": team, "opp": b.opp(team), "runner": p.actor, "defender": defender,
             "pos": md.positions[md.player_index(defender)], "d": p.measures["defender_displacement_m"],
             "benef": p.measures["beneficiary"], "served": served}
    signals = {"defender_displacement_m": p.measures["defender_displacement_m"], "space_value_gain": gain}
    confidence = 0.6 + (0.2 if served else 0.0) + (0.1 if gain >= 0.15 else 0.0)
    b.add("decoy_run", "decoy_run", p.t_end + 1.0, p.period, facts, signals,
          {"teams": [team], "players": [p.actor, defender, facts["benef"]]}, confidence, p.significance, _evidence(p))


def _chain(b: Builder, p: Pattern, by_id: dict[str, Pattern]) -> None:
    xg = float(p.measures["xg"])
    goal = p.measures["outcome"] == "goal"
    decoys = [by_id[i] for i in p.evidence.patterns if by_id[i].type == "decoy_run" and by_id[i].affected]
    if not goal and xg < 0.15 and not decoys:
        return
    team = p.team or ""
    facts = {"team": team, "opp": b.opp(team), "outcome": p.measures["outcome"], "shooter": p.actor, "xg": xg,
             "passes": p.measures["passes"], "sec": p.measures["seconds"]}
    players = [p.actor]
    key = "chain"
    if decoys:
        facts.update(decoy=decoys[0].actor, defender=decoys[0].affected[0])
        players += [decoys[0].actor, decoys[0].affected[0]]
        key = "chain_decoy"
    signals = {"xg": xg, "passes": float(p.measures["passes"]), "seconds": float(p.measures["seconds"])}
    b.add("chain", key, p.t_end + 1.0, p.period, facts, signals, {"teams": [team], "players": players}, 0.9,
          max(p.significance, 0.9 if goal else 0.0), _evidence(p, p.evidence.events))


def _simple(b: Builder, p: Pattern, by_id: dict[str, Pattern]) -> None:
    team = p.team or ""
    m = p.measures
    if p.type == "momentum_swing":
        drivers = list(dict.fromkeys(by_id[i].type for i in p.evidence.patterns))[:3]
        b.add("momentum_swing", "momentum_swing", p.t_start, p.period, {"team": team, "opp": b.opp(team),
              "drivers": drivers}, {"balance": float(m["balance"])}, {"teams": [team]}, 0.65, p.significance,
              _evidence(p))
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
    elif p.type == "fatigue":
        facts = {"team": team, "player": p.actor, "pct": m["high_intensity_share_change_pct"],
                 "now": m["top_speed_kmh_now"], "early": m["top_speed_kmh_early"], "focus": p.actor}
        b.add("fatigue", "fatigue", p.t_end, p.period, facts, {"top_speed_kmh": [facts["early"], facts["now"]]},
              {"teams": [team], "players": [p.actor]}, 0.7, p.significance, _evidence(p))


def _match_state(b: Builder) -> None:
    previous = None
    for s in b.a.state:
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


def draft_insights(a: Analysis) -> list[Draft]:
    b = Builder(a)
    by_id = {p.id: p for p in a.patterns}
    for p in a.patterns:
        if p.type == "pressure_shift":
            _pressure_shift(b, p)
        elif p.type == "decoy_run":
            _decoy(b, p)
        elif p.type == "chain":
            _chain(b, p, by_id)
        else:
            _simple(b, p, by_id)
    _match_state(b)
    return _route(b.drafts)


def _route(drafts: list[Draft]) -> list[Draft]:
    """Drop repeats and keep the stronger of two insights about the same team that would land too close together."""
    drafts.sort(key=lambda d: (d.insight.period, d.insight.t))
    kept: list[Draft] = []
    last_seen: dict[tuple, float] = {}
    for d in drafts:
        team = (d.insight.entities.get("teams") or [""])[0]
        gap = REPEAT_GAP_S.get(d.insight.type)
        if gap is not None:
            key = (d.insight.type, d.facts.get("runner") or team)
            absolute = d.insight.t + (10_000.0 if d.insight.period == 2 else 0.0)
            if absolute - last_seen.get(key, -1e9) < gap:
                continue
            last_seen[key] = absolute
        clash = next((k for k in reversed(kept) if k.insight.period == d.insight.period
                      and (k.insight.entities.get("teams") or [""])[0] == team
                      and d.insight.t - k.insight.t < MIN_GAP_S), None)
        goal = d.facts.get("outcome") == "goal"
        if clash is None or goal:
            kept.append(d)
        elif d.insight.significance > clash.insight.significance and clash.facts.get("outcome") != "goal":
            kept[kept.index(clash)] = d
    for k, d in enumerate(kept, 1):
        d.insight.id = f"in_{k}"
    return kept

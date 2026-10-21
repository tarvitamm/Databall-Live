"""Causal chains: the on-ball and off-ball actions that led to each shot."""

from __future__ import annotations

from ..contracts import Evidence, Pattern
from .match import MatchData
from .onball import ShotMetrics
from .possession import Possession

LOOKBACK_S = 15.0
OFF_BALL = {"run_in_behind", "checking_run", "overlap_run", "forward_run", "decoy_run", "overload",
            "between_lines_gap", "line_breaking_pass", "difficult_pass"}


def shot_chains(md: MatchData, poss: Possession, shots: list[ShotMetrics], patterns: list[Pattern],
                start_id: int = 1) -> list[Pattern]:
    out: list[Pattern] = []
    n = start_id
    events = {e["id"]: e for e in md.events}
    for s in shots:
        shot = events[s.event]
        code, period, t_shot = shot["team"], shot["period"], shot["t"]
        spell_start = t_shot - LOOKBACK_S
        for team, f0, f1 in poss.spells:
            if f0 <= s.frame <= f1 + md.hz and team == s.team:
                spell_start = max(spell_start, float(md.t[f0]) - 1.0)
                break
        links = []
        on_ball = [e for e in md.events if e.get("team") == code and e["period"] == period
                   and spell_start <= e["t"] < t_shot and e["type"] in ("pass", "carry", "ball_recovery",
                                                                       "interception", "tackle")]
        for e in on_ball:
            links.append({"t": e["t"], "kind": e["type"], "actor": e.get("player"), "ref": e["id"],
                          "detail": e.get("outcome") or ""})
        off_ball = [p for p in patterns if p.team == code and p.period == period and p.type in OFF_BALL
                    and p.t_end >= spell_start and p.t_start <= t_shot]
        for p in off_ball:
            links.append({"t": p.t_start, "kind": p.type, "actor": p.actor, "ref": p.id,
                          "detail": ",".join(p.affected)})
        links.sort(key=lambda x: x["t"])
        passes = sum(1 for x in links if x["kind"] == "pass" and x["detail"] == "complete")
        measures: dict[str, float | str] = {
            "outcome": s.outcome, "xg": s.xg if s.xg is not None else -1.0, "passes": passes,
            "off_ball_links": len(off_ball), "seconds": round(t_shot - spell_start, 1),
            "links": ";".join(f"{x['t']:.1f}|{x['kind']}|{x['actor'] or ''}|{x['detail']}" for x in links),
        }
        decoys = [p for p in off_ball if p.type == "decoy_run"]
        significance = min(1.0, 0.3 + (s.xg or 0.0) + 0.15 * len(decoys) + (0.3 if s.outcome == "goal" else 0.0))
        out.append(Pattern(id=f"pt_{n}", match=md.meta.match, type="chain", period=period, t_start=spell_start,
                           t_end=t_shot, actor=shot["player"], team=code,
                           affected=sorted({a for p in decoys for a in p.affected}), measures=measures,
                           evidence=Evidence(events=[x["ref"] for x in links if x["ref"].startswith("ev_")] + [s.event],
                                             patterns=[p.id for p in off_ball], window=(spell_start, t_shot)),
                           significance=round(significance, 2)))
        n += 1
    return out

"""Box score from a simulated match, used for quick checks and the realism report."""

from __future__ import annotations

from collections import Counter

import numpy as np

from .engine import HZ, MatchEngine


def box_score(engine: MatchEngine) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    total_poss = max(1, sum(engine.stats.possession_ticks))
    for team, club in enumerate(engine.clubs):
        ev = [e for e in engine.events if e.get("team") == club.code]
        kinds = Counter(e["type"] for e in ev)
        passes = [e for e in ev if e["type"] == "pass"]
        complete = sum(1 for e in passes if e.get("outcome") == "complete")
        shots = [e for e in ev if e["type"] == "shot"]
        on_target = sum(1 for e in shots if e.get("outcome") in ("goal", "saved"))
        outfield = [i for i in engine.members[team] if i != engine.gk[team]]
        out[club.code] = {
            "goals": kinds["goal"],
            "shots": len(shots),
            "on_target": on_target,
            "passes": len(passes),
            "pass_completion_pct": round(100.0 * complete / max(1, len(passes)), 1),
            "carries": kinds["carry"],
            "tackles_won": sum(1 for e in ev if e["type"] == "tackle" and e.get("outcome") == "won"),
            "interceptions": kinds["interception"],
            "pressures": kinds["pressure"],
            "fouls": kinds["foul"],
            "possession_pct": round(100.0 * engine.stats.possession_ticks[team] / total_poss, 1),
            "distance_km_outfield_avg": round(float(np.mean(engine.stats.distance[outfield])) / 1000.0, 2),
            "top_speed_kmh": round(float(np.max(engine.stats.top_speed[engine.members[team]])) * 3.6, 1),
            "runs": sum(1 for r in engine.run_log if r.team == club.code),
        }
    out["match"] = {"ball_in_play_min": round(engine.stats.ball_in_play_ticks / HZ / 60.0, 1),
                    "events": len(engine.events)}
    return out


def format_box_score(score: dict[str, dict[str, float]], home: str, away: str) -> str:
    rows = [k for k in score[home]]
    width = max(len(r) for r in rows) + 2
    lines = [f"{'':{width}}{home:>8}{away:>8}", f"{'score':{width}}{score[home]['goals']:>8}{score[away]['goals']:>8}"]
    for r in rows:
        if r == "goals":
            continue
        lines.append(f"{r:{width}}{score[home][r]:>8}{score[away][r]:>8}")
    lines.append(f"ball in play: {score['match']['ball_in_play_min']} min, events: {score['match']['events']}")
    return "\n".join(lines)

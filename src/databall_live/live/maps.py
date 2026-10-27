"""Event maps per team so far, turned so each team attacks towards x = 105."""

from __future__ import annotations

from ..stats.match import MatchData
from .commentary import attacking

FINAL_THIRD = 70.0
KINDS = ("shots", "passes", "dribbles", "decoys", "pressing", "attacking", "duels", "defending")


def _upto(period: int, t: float, at: tuple[int, float]) -> bool:
    return at[0] < period or (at[0] == period and at[1] <= t)


def _xy(md: MatchData, code: str, period: int, xy) -> list[float]:
    return [round(v, 1) for v in attacking(md, code, period, [float(xy[0]), float(xy[1])])]


def maps(md: MatchData, patterns: list[dict], xg: dict[str, float], period: int, t: float) -> dict:
    out = {code: {k: [] for k in KINDS} for code in md.codes}
    for e in md.events:
        code, kind = e.get("team"), e["type"]
        if not code or "start" not in e or not _upto(period, t, (e["period"], e["t"])):
            continue
        m = out[code]
        a = _xy(md, code, e["period"], e["start"])
        b = _xy(md, code, e["period"], e["end"]) if "end" in e else a
        enters = a[0] < FINAL_THIRD <= b[0]
        if kind == "shot":
            m["shots"].append([*a, round(xg.get(e["id"], 0.0), 2), e.get("outcome"), e.get("player")])
        elif kind == "pass":
            done = int(e.get("outcome") == "complete")
            m["passes"].append([*a, *b, done])
            if enters:
                m["attacking"].append([*a, *b, done])
        elif kind == "carry":
            m["dribbles"].append([*a, *b])
            if enters:
                m["attacking"].append([*a, *b, 1])
        elif kind == "pressure":
            m["pressing"].append(a)
        elif kind == "tackle":
            m["duels"].append([*a, int(e.get("outcome") == "won")])
        elif kind in ("interception", "clearance", "ball_recovery"):
            m["defending"].append([*a, kind])
    for p in patterns:
        if p["type"] != "decoy_run" or p.get("team") not in out or not _upto(period, t, (p["period"], p["t_end"])):
            continue
        i = md.ids.index(p["actor"])
        start, end = md.pos[md.frame_at(p["period"], p["t_start"]), i], md.pos[md.frame_at(p["period"], p["t_end"]), i]
        out[p["team"]]["decoys"].append([*_xy(md, p["team"], p["period"], start),
                                         *_xy(md, p["team"], p["period"], end), p["actor"]])
    return out

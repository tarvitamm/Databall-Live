"""Live fantasy points for every player, scored from the match so far with fantasy league rules plus a point for every
two decoy runs."""

from __future__ import annotations

from ..stats.match import MatchData

GOAL = {"GK": 6, "DEF": 6, "MID": 5, "FWD": 4}
CLEAN_SHEET = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}
DEFENCE_TARGET = {"GK": 10, "DEF": 10, "MID": 12, "FWD": 12}
ASSIST_WINDOW_S = 15.0
BONUS = (3, 2, 1)


def role(position: str) -> str:
    if position == "GK":
        return "GK"
    if position in ("ST", "CF", "LW", "RW"):
        return "FWD"
    if position.endswith("B") or position in ("CB", "LCB", "RCB"):
        return "DEF"
    return "MID"


def _upto(item: dict, period: int, t: float, key: str = "t") -> bool:
    return item["period"] < period or (item["period"] == period and item[key] <= t)


def fantasy(md: MatchData, goals: list[tuple[int, float, str, str]], patterns: list[dict], period: int,
            t: float, starts: dict[int, float]) -> list[dict]:
    """Points per player at this moment, best first, with the lines that make them up."""
    played = t - starts[period] + (45 * 60 if period == 2 else 0)
    events = [e for e in md.events if _upto(e, period, t)]
    done = [g for g in goals if g[0] < period or (g[0] == period and g[1] <= t)]
    conceded = {code: sum(1 for g in done if g[2] != code) for code in md.codes}
    passes = [e for e in events if e["type"] == "pass" and e.get("outcome") == "complete"]
    rows = []
    for i, pid in enumerate(md.ids):
        code = md.codes[int(md.team[i])]
        r = role(md.positions[i])
        mine = [e for e in events if e.get("player") == pid]
        scored = [g for g in done if g[3] == pid]
        assists = sum(1 for g in done if g[2] == code and any(
            e.get("recipient") == g[3] and e["player"] == pid and e["period"] == g[0]
            and g[1] - ASSIST_WINDOW_S <= e["t"] <= g[1] for e in passes))
        defence = sum(1 for e in mine if e["type"] in ("interception", "clearance")
                      or (e["type"] == "tackle" and e.get("outcome") == "won")
                      or (e["type"] == "ball_recovery" and r in ("MID", "FWD")))
        saves = sum(1 for e in events if r == "GK" and e["type"] == "shot" and e.get("outcome") == "saved"
                    and e.get("team") != code)
        decoys = sum(1 for p in patterns if p["type"] == "decoy_run" and p.get("actor") == pid
                     and _upto(p, period, t, "t_end"))
        lines = [
            ("played", 1, 2 if played >= 60 * 60 else 1),
            ("goals", len(scored), len(scored) * GOAL[r]),
            ("assists", assists, assists * 3),
            ("clean_sheet", 1, CLEAN_SHEET[r]) if played >= 60 * 60 and conceded[code] == 0 else None,
            ("conceded", conceded[code], -(conceded[code] // 2)) if r in ("GK", "DEF") else None,
            ("defence", defence, 2 if defence >= DEFENCE_TARGET[r] else 0),
            ("saves", saves, saves // 3) if r == "GK" else None,
            ("offball", decoys, decoys // 2),
        ]
        items = [[k, n, pts] for k, n, pts in (x for x in lines if x) if n or pts]
        touches = sum(1 for e in passes if e["player"] == pid) + defence
        rows.append({"id": pid, "team": code, "role": r, "items": items,
                     "points": sum(x[2] for x in items), "touches": touches})
    rows.sort(key=lambda x: (-x["points"], -x["touches"]))
    for bonus, row in zip(BONUS, rows, strict=False):
        row["items"].append(["bonus", 1, bonus])
        row["points"] += bonus
    for row in rows:
        row.pop("touches")
    return rows

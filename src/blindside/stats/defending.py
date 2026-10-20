"""Out-of-possession patterns: counter-pressing, recovery runs, line movements, gaps between the lines, overloads."""

from __future__ import annotations

import numpy as np

from ..contracts import Evidence, Pattern
from .kinematics import Kinematics
from .match import LENGTH, MatchData
from .possession import Possession
from .shape import Shape


class PatternIds:
    def __init__(self, start: int) -> None:
        self.n = start

    def next(self) -> str:
        self.n += 1
        return f"pt_{self.n - 1}"


def turnovers(md: MatchData, poss: Possession, max_gap_s: float = 2.0) -> list[tuple[int, int]]:
    """(team that lost the ball, first frame of the opponent's spell) for open-play changes of possession."""
    out = []
    for (t0, _, end0), (t1, start1, _) in zip(poss.spells, poss.spells[1:], strict=False):
        if t0 != t1 and md.period[end0] == md.period[start1] and (start1 - end0) / md.hz <= max_gap_s:
            if poss.in_play[end0:start1 + 1].all():
                out.append((t0, start1))
    return out


def _pattern(md: MatchData, ids: PatternIds, kind: str, f0: int, f1: int, team: int, actor: int | None,
             affected: list[int], measures: dict, significance: float) -> Pattern:
    t0, t1 = float(md.t[f0]), float(md.t[f1])
    return Pattern(id=ids.next(), match=md.meta.match, type=kind, period=int(md.period[f0]), t_start=t0, t_end=t1,
                   actor=md.ids[actor] if actor is not None else None, team=md.codes[team],
                   affected=[md.ids[a] for a in affected], measures=measures, evidence=Evidence(window=(t0, t1)),
                   significance=significance)


def counter_presses(md: MatchData, kin: Kinematics, poss: Possession, lost: list[tuple[int, int]],
                    ids: PatternIds) -> list[Pattern]:
    out = []
    for team, f in lost:
        end = min(f + 3 * md.hz, len(md.t) - 1)
        if md.period[end] != md.period[f]:
            continue
        mine = md.outfield(team)
        best, first = 0, None
        for k in range(f, end + 1):
            rel = md.pos[k, mine] - md.ball[k, :2]
            d = np.linalg.norm(rel, axis=1)
            closing = np.einsum("ij,ij->i", kin.vel[k, mine], -rel / np.maximum(d, 1e-6)[:, None]) > 2.0
            n = int(np.sum((d < 4.0) & closing))
            if n > best:
                best, first = n, int(mine[np.argmin(d)])
        if best < 2:
            continue
        back = np.flatnonzero(poss.team[f:min(f + 5 * md.hz, len(md.t) - 1) + 1] == team)
        regained = len(back) > 0
        seconds = round(float(back[0]) / md.hz, 1) if regained else None
        measures = {"pressers": best, "regained": str(regained).lower()}
        if seconds is not None:
            measures["seconds_to_regain"] = seconds
        carrier = poss.carrier[f]
        out.append(_pattern(md, ids, "counter_press", f, end, team, first, [int(carrier)] if carrier >= 0 else [],
                            measures, 0.45 if regained else 0.25))
    return out


def recovery_runs(md: MatchData, kin: Kinematics, lost: list[tuple[int, int]], ids: PatternIds) -> list[Pattern]:
    out = []
    for team, f in lost:
        end = min(f + 8 * md.hz, len(md.t) - 1)
        if md.period[end] != md.period[f]:
            continue
        frames = np.arange(f, end + 1)
        ball_tf = md.to_team_frame(md.ball[frames, :2], team, frames=frames)
        for i in md.outfield(team):
            fast = kin.speed[frames, i] >= 6.0
            if fast.sum() < md.hz:
                continue
            p = md.to_team_frame(md.pos[frames, i], team, frames=frames)
            k = int(np.argmin(p[:, 0]))
            back = p[0, 0] - p[k, 0]
            goal_side = bool(p[k, 0] < ball_tf[k, 0])
            if back < 20.0 or not goal_side:
                continue
            measures = {"distance_back_m": round(float(back), 1),
                        "top_speed_kmh": round(float(kin.speed[frames, i].max()) * 3.6, 1),
                        "ended_goal_side": str(goal_side).lower()}
            out.append(_pattern(md, ids, "recovery_run", f, f + k, team, int(i), [], measures, 0.4))
    return out


def line_movements(md: MatchData, poss: Possession, shape: Shape, ids: PatternIds, step_m: float = 8.0,
                   within_s: float = 3.0) -> list[Pattern]:
    out = []
    lag = int(within_s * md.hz)
    for team in (0, 1):
        out_of_poss = (poss.team == 1 - team) & poss.in_play
        line = shape.def_line[:, team]
        k = 0
        n = len(md.t) - lag
        while k < n:
            if not (out_of_poss[k] and out_of_poss[k + lag] and md.period[k] == md.period[k + lag]):
                k += 1
                continue
            delta = line[k + lag] - line[k]
            ball = md.to_team_frame(md.ball[[k, k + lag], :2], team, frames=np.array([k, k + lag]))[:, 0]
            retreat_with_ball = delta < 0 and ball[0] - ball[1] >= 10.0
            if abs(delta) >= step_m and not retreat_with_ball:
                kind = "line_step_up" if delta > 0 else "line_drop"
                measures = {"from_m": round(float(line[k]), 1), "to_m": round(float(line[k + lag]), 1)}
                out.append(_pattern(md, ids, kind, k, k + lag, team, None, [], measures, 0.2))
                k += 20 * md.hz
            else:
                k += md.hz // 2
    return out


def between_lines_gaps(md: MatchData, poss: Possession, shape: Shape, ids: PatternIds, gap_m: float = 24.0,
                       min_s: float = 4.0) -> list[Pattern]:
    out = []
    passes = [e for e in md.events if e["type"] == "pass" and e.get("outcome") == "complete"]
    for team in (0, 1):
        open_gap = (poss.team == 1 - team) & poss.in_play & (shape.gap[:, team] > gap_m)
        idx = np.flatnonzero(open_gap)
        if len(idx) == 0:
            continue
        splits = np.flatnonzero(np.diff(idx) > 1) + 1
        for seg in np.split(idx, splits):
            if len(seg) < min_s * md.hz:
                continue
            f0, f1 = int(seg[0]), int(seg[-1])
            used_by = None
            for e in passes:
                if e["team"] != md.codes[1 - team] or e["period"] != md.period[f0]:
                    continue
                if not md.t[f0] <= e["t"] <= md.t[f1]:
                    continue
                f = md.frame_at(e["period"], e["t"])
                x = e["end"][0] if md.sign(team, e["period"]) == 1 else LENGTH - e["end"][0]
                if shape.def_line[f, team] < x < shape.mid_line[f, team]:
                    used_by = md.player_index(e["recipient"])
                    break
            if used_by is None and shape.gap[seg, team].max() < gap_m + 3.0:
                continue
            measures = {"max_gap_m": round(float(shape.gap[seg, team].max()), 1),
                        "seconds": round(len(seg) / md.hz, 1), "exploited": str(used_by is not None).lower()}
            affected = [used_by] if used_by is not None else []
            out.append(_pattern(md, ids, "between_lines_gap", f0, f1, team, None, affected, measures,
                                0.45 if used_by is not None else 0.15))
    return out


def overloads(md: MatchData, poss: Possession, ids: PatternIds, radius: float = 20.0, edge: int = 2,
              min_s: float = 1.5) -> list[Pattern]:
    out = []
    step = md.hz // 2
    for team in (0, 1):
        frames = np.flatnonzero((poss.team == team) & poss.in_play)[::step]
        if len(frames) == 0:
            continue
        ball = md.ball[frames, :2]
        mine = np.linalg.norm(md.pos[frames][:, md.members(team)] - ball[:, None, :], axis=2) < radius
        theirs = np.linalg.norm(md.pos[frames][:, md.members(1 - team)] - ball[:, None, :], axis=2) < radius
        ball_tf = md.to_team_frame(ball, team, frames=frames)
        hit = (mine.sum(1) - theirs.sum(1) >= edge) & (ball_tf[:, 0] > LENGTH / 2)
        k = 0
        while k < len(frames):
            if not hit[k]:
                k += 1
                continue
            j = k
            while j + 1 < len(frames) and hit[j + 1] and frames[j + 1] - frames[j] <= step:
                j += 1
            if (frames[j] - frames[k]) / md.hz >= min_s:
                y = ball_tf[k, 1]
                side = "right" if y < 22.7 else ("left" if y > 45.3 else "centre")
                measures = {"attackers": int(mine[k].sum()), "defenders": int(theirs[k].sum()), "side": side}
                out.append(_pattern(md, ids, "overload", int(frames[k]), int(frames[j]), team, None, [], measures,
                                    0.3))
            k = j + 1
    return out

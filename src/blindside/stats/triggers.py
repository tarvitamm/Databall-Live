"""On-screen triggers: speed and distance name tags, fast shots, difficult and line-breaking passes, fatigue."""

from __future__ import annotations

import numpy as np

from ..contracts import Evidence, Pattern
from .kinematics import HIGH_INTENSITY_MS, Kinematics
from .match import MatchData
from .onball import PassMetrics, ShotMetrics

SPRINT_TAG_KMH = 30.0
TAG_COOLDOWN_S = 180.0
MILESTONES_KM = (10.0, 11.0, 12.0)


def _p(md: MatchData, n: int, kind: str, f: int, team: int, actor: int | None, measures: dict,
       significance: float, events: list[str] | None = None) -> Pattern:
    t = float(md.t[f])
    return Pattern(id=f"pt_{n}", match=md.meta.match, type=kind, period=int(md.period[f]), t_start=t, t_end=t,
                   actor=md.ids[actor] if actor is not None else None, team=md.codes[team], measures=measures,
                   evidence=Evidence(events=events or [], window=(t - 3.0, t + 3.0)), significance=significance)


def triggers(md: MatchData, kin: Kinematics, passes: list[PassMetrics], shots: list[ShotMetrics],
             start_id: int = 1) -> list[Pattern]:
    out: list[Pattern] = []
    n = start_id

    for i in range(len(md.ids)):
        team = int(md.team[i])
        kmh = kin.speed[:, i] * 3.6
        last_tag = -np.inf
        fast = np.flatnonzero(kmh >= SPRINT_TAG_KMH)
        if len(fast):
            for seg in np.split(fast, np.flatnonzero(np.diff(fast) > 1) + 1):
                peak = int(seg[np.argmax(kmh[seg])])
                t_abs = peak / md.hz
                if t_abs - last_tag < TAG_COOLDOWN_S:
                    continue
                last_tag = t_abs
                out.append(_p(md, n, "speed_tag", peak, team, i, {"speed_kmh": round(float(kmh[peak]), 1)}, 0.3))
                n += 1
        dist_km = np.cumsum(kin.speed[:, i]) / md.hz / 1000.0
        for km in MILESTONES_KM:
            hit = np.flatnonzero(dist_km >= km)
            if len(hit):
                out.append(_p(md, n, "distance_milestone", int(hit[0]), team, i, {"distance_km": km}, 0.25))
                n += 1
    top = kin.speed.max(axis=1) * 3.6
    warmup = (md.period == 1) & (md.t < 600)
    match_top = float(top[warmup].max()) if warmup.any() else 0.0
    for f in np.flatnonzero(~warmup & (top > match_top + 0.3)):
        if top[f] > match_top + 0.3:
            match_top = float(top[f])
            i = int(np.argmax(kin.speed[f]))
            out.append(_p(md, n, "match_top_speed", int(f), int(md.team[i]), i, {"speed_kmh": round(match_top, 1)},
                          0.4))
            n += 1
    for s in shots:
        if s.speed_kmh >= 100.0:
            out.append(_p(md, n, "shot_speed", s.frame, s.team, s.shooter,
                          {"speed_kmh": s.speed_kmh, "outcome": s.outcome}, 0.35, [s.event]))
            n += 1
    for p in passes:
        if not p.complete:
            continue
        if p.difficulty is not None and p.difficulty >= 8.0:
            out.append(_p(md, n, "difficult_pass", p.frame, p.team, p.passer,
                          {"difficulty": p.difficulty, "distance_m": p.distance_m, "speed_kmh": p.speed_kmh}, 0.35,
                          [p.event]))
            n += 1
        if p.lines_broken >= 2:
            out.append(_p(md, n, "line_breaking_pass", p.frame, p.team, p.passer,
                          {"lines_broken": p.lines_broken, "distance_m": p.distance_m, "speed_kmh": p.speed_kmh}, 0.4,
                          [p.event]))
            n += 1
    return out


def fatigue(md: MatchData, kin: Kinematics, start_id: int = 1, bin_min: float = 15.0) -> list[Pattern]:
    """Players whose high-intensity running and top speed have both clearly dropped since the first 15 minutes."""
    out: list[Pattern] = []
    n = start_id
    clock = md.t / 60.0
    bins = np.floor(clock / bin_min).astype(int)
    for i in range(len(md.ids)):
        hi = kin.speed[:, i] >= HIGH_INTENSITY_MS
        first = bins == 0
        hi0 = hi[first].mean()
        top0 = kin.speed[first, i].max()
        if hi0 < 0.01:
            continue
        for b in range(4, int(bins.max()) + 1):
            sel = bins == b
            if sel.sum() < 60 * md.hz:
                continue
            hi_b, top_b = hi[sel].mean(), kin.speed[sel, i].max()
            if hi_b <= 0.65 * hi0 and top_b <= 0.93 * top0:
                f = int(np.flatnonzero(sel)[-1])
                out.append(_p(md, n, "fatigue", f, int(md.team[i]), i,
                              {"high_intensity_share_change_pct": round(100.0 * (hi_b / hi0 - 1.0), 0),
                               "top_speed_kmh_now": round(float(top_b) * 3.6, 1),
                               "top_speed_kmh_early": round(float(top0) * 3.6, 1)}, 0.35))
                n += 1
                break
    return out

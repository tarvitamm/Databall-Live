"""Pressing intensity per minute, and pressure shifts confirmed by two independent signal families."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..contracts import Evidence, Pattern
from .match import LENGTH, MatchData
from .possession import Possession
from .shape import Shape

RECENT_MIN = 10
BASELINE_MIN = 15
CONFIRM_MIN = 4
DEF_ACTIONS = {"tackle", "interception", "foul"}
REGAINS = {"ball_recovery", "interception"}
FAMILY = {"pressures_per_min": "intensity", "ppda": "intensity", "line_height_m": "position",
          "high_regains_per_10": "outcome"}
MIN_ACTIONS_FOR_PPDA = 3
THRESHOLDS = {"pressures_ratio": 1.35, "pressures_abs": 1.0, "ppda_ratio": 0.65, "ppda_abs": 2.0,
              "line_m": 4.0, "regains_per_10": 1.5}


@dataclass
class MinuteBin:
    team: int
    period: int
    t_end: float
    opp_possession_s: float = 0.0
    pressures: int = 0
    opp_passes: int = 0
    def_actions: int = 0
    regains: int = 0
    line_sum: float = 0.0
    line_frames: int = 0


@dataclass
class PressWindow:
    team: int
    period: int
    t_end: float
    minutes: int
    opp_possession_min: float
    pressures_per_min: float
    ppda: float
    def_actions: int
    line_height_m: float
    high_regains_per_10: float


def _team_frame_x(md: MatchData, e: dict, team: int) -> float | None:
    if e.get("start") is None:
        return None
    x = e["start"][0]
    return x if md.sign(team, e["period"]) == 1 else LENGTH - x


def minute_bins(md: MatchData, poss: Possession, shape: Shape) -> list[MinuteBin]:
    """Per-minute raw counts for each team as the pressing side, in match order across both halves."""
    bins: list[MinuteBin] = []
    for period in (1, 2):
        in_period = md.period == period
        t0, t_last = float(md.t[in_period][0]), float(md.t[in_period][-1])
        edges = np.arange(t0, t_last + 60.0, 60.0)
        evs = [e for e in md.events if e["period"] == period]
        for team in (0, 1):
            opp = 1 - team
            code, opp_code = md.codes[team], md.codes[opp]
            for lo, hi in zip(edges[:-1], edges[1:], strict=True):
                b = MinuteBin(team=team, period=period, t_end=float(hi))
                frames = in_period & (md.t > lo) & (md.t <= hi) & (poss.team == opp)
                b.opp_possession_s = frames.sum() / md.hz
                b.line_sum = float(shape.def_line[frames, team].sum())
                b.line_frames = int(frames.sum())
                for e in evs:
                    if not lo < e["t"] <= hi:
                        continue
                    if e["type"] == "pressure" and e.get("team") == code:
                        b.pressures += 1
                    elif e["type"] == "pass" and e.get("team") == opp_code:
                        x = _team_frame_x(md, e, opp)
                        b.opp_passes += int(x is not None and x < 0.6 * LENGTH)
                    if e.get("team") == code and e["type"] in DEF_ACTIONS:
                        x = _team_frame_x(md, e, team)
                        b.def_actions += int(x is not None and x > 0.4 * LENGTH)
                    won = e["type"] in REGAINS or (e["type"] == "tackle" and e.get("outcome") == "won")
                    if e.get("team") == code and won:
                        x = _team_frame_x(md, e, team)
                        b.regains += int(x is not None and x > LENGTH - 35.0)
                bins.append(b)
    return bins


def window(bins: list[MinuteBin]) -> PressWindow:
    opp_min = sum(b.opp_possession_s for b in bins) / 60.0
    actions = sum(b.def_actions for b in bins)
    frames = sum(b.line_frames for b in bins)
    return PressWindow(
        team=bins[-1].team, period=bins[-1].period, t_end=bins[-1].t_end, minutes=len(bins),
        opp_possession_min=round(opp_min, 2),
        pressures_per_min=round(sum(b.pressures for b in bins) / max(opp_min, 0.5), 2),
        ppda=round(sum(b.opp_passes for b in bins) / max(actions, 1), 2), def_actions=actions,
        line_height_m=round(sum(b.line_sum for b in bins) / frames, 1) if frames else float("nan"),
        high_regains_per_10=round(10.0 * sum(b.regains for b in bins) / len(bins), 2),
    )


def pressing_windows(md: MatchData, poss: Possession, shape: Shape) -> list[PressWindow]:
    """Rolling 10-minute windows, one per minute per team, for display and the insight layer."""
    bins = minute_bins(md, poss, shape)
    out = []
    for team in (0, 1):
        seq = [b for b in bins if b.team == team]
        for k in range(9, len(seq)):
            out.append(window(seq[k - 9:k + 1]))
    return out


def _signals(base: PressWindow, recent: PressWindow) -> dict[str, int]:
    """+1 where the team now presses harder, -1 where softer, 0 where no clear change."""
    th = THRESHOLDS
    s = {}
    p0, p1 = base.pressures_per_min, recent.pressures_per_min
    s["pressures_per_min"] = (1 if p1 >= p0 * th["pressures_ratio"] and p1 - p0 >= th["pressures_abs"]
                              else -1 if p1 <= p0 / th["pressures_ratio"] and p0 - p1 >= th["pressures_abs"] else 0)
    q0, q1 = base.ppda, recent.ppda
    if min(base.def_actions, recent.def_actions) < MIN_ACTIONS_FOR_PPDA:
        s["ppda"] = 0
    else:
        s["ppda"] = (1 if q1 <= q0 * th["ppda_ratio"] and q0 - q1 >= th["ppda_abs"]
                     else -1 if q1 >= q0 / th["ppda_ratio"] and q1 - q0 >= th["ppda_abs"] else 0)
    l0, l1 = base.line_height_m, recent.line_height_m
    s["line_height_m"] = (0 if np.isnan(l0) or np.isnan(l1)
                          else 1 if l1 - l0 >= th["line_m"] else -1 if l0 - l1 >= th["line_m"] else 0)
    r0, r1 = base.high_regains_per_10, recent.high_regains_per_10
    s["high_regains_per_10"] = (1 if r1 - r0 >= th["regains_per_10"]
                                else -1 if r0 - r1 >= th["regains_per_10"] else 0)
    return s


def _call(base: PressWindow, recent: PressWindow) -> tuple[int, dict[str, int]] | None:
    sig = _signals(base, recent)
    for direction in (1, -1):
        if len({FAMILY[name] for name, v in sig.items() if v == direction}) >= 2:
            return direction, sig
    return None


def shifts_from_bins(md: MatchData, bins: list[MinuteBin], start_id: int = 1) -> list[Pattern]:
    patterns: list[Pattern] = []
    n = start_id
    for team in (0, 1):
        seq = [b for b in bins if b.team == team]
        calls: list[tuple[int, PressWindow, PressWindow, dict[str, int]] | None] = []
        for k in range(len(seq)):
            if k + 1 < RECENT_MIN + BASELINE_MIN:
                calls.append(None)
                continue
            recent = window(seq[k + 1 - RECENT_MIN:k + 1])
            base = window(seq[k + 1 - RECENT_MIN - BASELINE_MIN:k + 1 - RECENT_MIN])
            c = _call(base, recent)
            calls.append((c[0], base, recent, c[1]) if c else None)
        quiet_until = -1
        for k, c in enumerate(calls):
            if c is None or k < quiet_until:
                continue
            following = calls[k + 1:k + CONFIRM_MIN]
            if len(following) < CONFIRM_MIN - 1 or any(f is None or f[0] != c[0] for f in following):
                continue
            direction, base, recent, sig = c
            agreeing = [name for name, v in sig.items() if v == direction]
            measures: dict[str, float | str] = {"direction": "harder" if direction == 1 else "softer",
                                                "signals": ",".join(agreeing)}
            for name in ("pressures_per_min", "ppda", "line_height_m", "high_regains_per_10"):
                measures[f"{name}_before"] = getattr(base, name)
                measures[f"{name}_after"] = getattr(recent, name)
            t_end = recent.t_end
            patterns.append(Pattern(
                id=f"pt_{n}", match=md.meta.match, type="pressure_shift", period=recent.period, t_start=t_end,
                t_end=t_end, team=md.codes[team], measures=measures,
                evidence=Evidence(window=(t_end - 60.0 * (RECENT_MIN + BASELINE_MIN), t_end)),
                significance=round(min(1.0, 0.5 + 0.15 * len(agreeing)), 2)))
            n += 1
            quiet_until = k + RECENT_MIN + BASELINE_MIN // 2
    return patterns


def detect_pressure_shifts(md: MatchData, poss: Possession, shape: Shape, start_id: int = 1) -> list[Pattern]:
    return shifts_from_bins(md, minute_bins(md, poss, shape), start_id)

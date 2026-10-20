"""Match state over time: control vs chaos per five minutes, momentum and its swings."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..contracts import Evidence, Pattern
from .match import LENGTH, WIDTH, MatchData
from .onball import PassMetrics, ShotMetrics
from .possession import Possession
from .value import zone_value

BIN_MIN = 5.0
CHAOS_BASELINE = {"turnovers": (3.16, 0.99), "under_pressure": (0.56, 0.15), "tackles": (1.55, 0.82)}
CHAOTIC_AT = 65
HALF_LIFE_S = 180.0
DRIVERS = {"pressure_shift", "decoy_run", "overload", "counter_press", "line_breaking_pass", "between_lines_gap",
           "fatigue", "chain"}


@dataclass
class StateBin:
    period: int
    t_end: float
    control: tuple[float, float]
    chaos: float
    label: str
    possession_share: tuple[float, float]
    territory: tuple[float, float]
    turnovers_per_min: float


def _tf_x(md: MatchData, xy, team: int, period: int) -> np.ndarray:
    p = np.asarray(xy, dtype=float)
    return p if md.sign(team, period) == 1 else np.array([LENGTH - p[0], WIDTH - p[1]])


def control_and_chaos(md: MatchData, poss: Possession, passes: list[PassMetrics]) -> list[StateBin]:
    out = []
    pressure_by_event = {p.event: p.under_pressure for p in passes}
    for period in (1, 2):
        sel = md.period == period
        t0, t1 = float(md.t[sel][0]), float(md.t[sel][-1])
        for lo in np.arange(t0, t1, BIN_MIN * 60):
            hi = lo + BIN_MIN * 60
            frames = sel & (md.t >= lo) & (md.t < hi) & poss.in_play
            if frames.sum() < 30 * md.hz:
                continue
            share, territory, per_spell = [], [], []
            for team in (0, 1):
                mine = frames & (poss.team == team)
                share.append(mine.sum() / frames.sum())
                ball_x = md.to_team_frame(md.ball[mine, :2], team, frames=np.flatnonzero(mine))[:, 0]
                territory.append(float((ball_x > LENGTH / 2).mean()) if len(ball_x) else 0.0)
                spells = [s for s in poss.spells
                          if s[0] == team and lo <= md.t[s[1]] < hi and md.period[s[1]] == period]
                n_pass = sum(1 for e in md.events if e["type"] == "pass" and e.get("outcome") == "complete"
                             and e["team"] == md.codes[team] and e["period"] == period and lo <= e["t"] < hi)
                per_spell.append(n_pass / max(len(spells), 1))
            minutes = frames.sum() / md.hz / 60
            changes = sum(1 for a, b in zip(poss.spells, poss.spells[1:], strict=False)
                          if a[0] != b[0] and md.period[b[1]] == period and lo <= md.t[b[1]] < hi)
            window = [e for e in md.events if e["period"] == period and lo <= e["t"] < hi]
            in_window = [pressure_by_event[e["id"]] for e in window if e["id"] in pressure_by_event]
            under = float(np.mean(in_window)) if in_window else 0.0
            tackles = sum(1 for e in window if e["type"] == "tackle") / max(minutes, 0.5)
            control = tuple(round(100 * float(np.clip(0.4 * share[t] + 0.3 * territory[t]
                                                      + 0.3 * min(per_spell[t] / 6.0, 1.0), 0, 1)), 0) for t in (0, 1))
            turnovers = changes / max(minutes, 0.5)
            z = [(v - CHAOS_BASELINE[k][0]) / CHAOS_BASELINE[k][1]
                 for k, v in (("turnovers", turnovers), ("under_pressure", under), ("tackles", tackles))]
            chaos = round(float(np.clip(50 + 15 * np.mean(z), 0, 100)), 0)
            if chaos >= CHAOTIC_AT:
                label = "chaotic"
            elif abs(control[0] - control[1]) >= 15:
                label = f"{md.codes[0 if control[0] > control[1] else 1]} in control"
            else:
                label = "balanced"
            out.append(StateBin(period=period, t_end=float(hi), control=control, chaos=chaos, label=label,
                                possession_share=(round(share[0], 2), round(share[1], 2)),
                                territory=(round(territory[0], 2), round(territory[1], 2)),
                                turnovers_per_min=round(turnovers, 2)))
    return out


def momentum(md: MatchData, passes: list[PassMetrics], shots: list[ShotMetrics]) -> np.ndarray:
    """Per-second threat balance (home minus away), each team's threat decaying with a 3-minute half-life."""
    seconds = np.round(md.t).astype(int)
    keys = sorted(set(zip(md.period.tolist(), seconds.tolist(), strict=True)))
    index = {k: n for n, k in enumerate(keys)}
    impulse = np.zeros((len(keys), 2))
    events = {e["id"]: e for e in md.events}
    for p in passes:
        if not p.complete:
            continue
        e = events[p.event]
        gain = float(zone_value(_tf_x(md, e["end"], p.team, e["period"]))
                     - zone_value(_tf_x(md, e["start"], p.team, e["period"])))
        impulse[index[(e["period"], int(round(e["t"])))], p.team] += max(gain, 0.0)
    for s in shots:
        e = events[s.event]
        impulse[index[(e["period"], int(round(e["t"])))], s.team] += s.xg or 0.1
    decay = 0.5 ** (1.0 / HALF_LIFE_S)
    level = np.zeros_like(impulse)
    for k in range(len(keys)):
        prev = level[k - 1] * decay if k and keys[k][0] == keys[k - 1][0] else 0.0
        level[k] = prev + impulse[k]
    return np.column_stack([np.array([k[0] for k in keys]), np.array([k[1] for k in keys]), level[:, 0] - level[:, 1]])


def momentum_swings(md: MatchData, series: np.ndarray, patterns: list[Pattern], start_id: int = 1,
                    hold_s: int = 120, floor: float = 0.05) -> list[Pattern]:
    out: list[Pattern] = []
    n = start_id
    for period in (1, 2):
        rows = series[series[:, 0] == period]
        side = np.sign(np.where(np.abs(rows[:, 2]) < floor, 0.0, rows[:, 2]))
        current = 0
        k = 0
        while k < len(rows):
            s = side[k]
            if s == 0 or s == current:
                k += 1
                continue
            if k + hold_s < len(rows) and np.all(side[k:k + hold_s] == s):
                team = 0 if s > 0 else 1
                t = float(rows[k, 1])
                drivers = [p for p in patterns if p.team == md.codes[team] and p.period == period
                           and p.type in DRIVERS and t - 300 <= p.t_start <= t]
                drivers.sort(key=lambda p: -p.significance)
                if current != 0:
                    out.append(Pattern(
                        id=f"pt_{n}", match=md.meta.match, type="momentum_swing", period=period, t_start=t, t_end=t,
                        team=md.codes[team],
                        measures={"balance": round(float(rows[k + hold_s - 1, 2]), 3),
                                  "drivers": ",".join(p.type for p in drivers[:4])},
                        evidence=Evidence(patterns=[p.id for p in drivers[:4]], window=(t - 300.0, t + hold_s)),
                        significance=round(min(1.0, 0.4 + 0.1 * len(drivers[:4])), 2)))
                    n += 1
                current = s
                k += hold_s
            else:
                k += 1
    return out

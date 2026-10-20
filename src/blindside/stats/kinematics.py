"""Smoothed velocity, speed and acceleration from 10 Hz positions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import savgol_filter

from .match import MatchData

SPRINT_MS = 25.2 / 3.6        # sprint threshold, 25.2 km/h
HIGH_INTENSITY_MS = 19.8 / 3.6
MAX_BALL_MS = 45.0          # faster means the ball was placed for a restart


@dataclass
class Kinematics:
    vel: np.ndarray       # (N, P, 2) m/s
    speed: np.ndarray     # (N, P) m/s
    accel: np.ndarray     # (N, P) m/s2, signed change in speed
    ball_speed: np.ndarray  # (N,) m/s, horizontal


def compute_kinematics(md: MatchData, window: int = 7, poly: int = 2) -> Kinematics:
    dt = 1.0 / md.hz
    vel = np.zeros_like(md.pos)
    ball_v = np.zeros((len(md.t), 2))
    for period in (1, 2):
        idx = np.flatnonzero(md.period == period)
        seg = md.pos[idx]
        vel[idx] = savgol_filter(seg, window, poly, deriv=1, delta=dt, axis=0, mode="interp")
        # a short window keeps the edge of each kick
        ball_v[idx] = savgol_filter(md.ball[idx, :2], 3, 1, deriv=1, delta=dt, axis=0, mode="interp")
    speed = np.linalg.norm(vel, axis=2)
    accel = np.zeros_like(speed)
    for period in (1, 2):
        idx = np.flatnonzero(md.period == period)
        accel[idx] = savgol_filter(speed[idx], window, poly, deriv=1, delta=dt, axis=0, mode="interp")
    ball_speed = np.linalg.norm(ball_v, axis=1)
    ball_speed[ball_speed > MAX_BALL_MS] = np.nan
    return Kinematics(vel=vel, speed=speed, accel=accel, ball_speed=ball_speed)


def count_sprints(speed: np.ndarray, hz: int, min_s: float = 1.0, merge_s: float = 0.5) -> int:
    """Spells above sprint speed lasting at least `min_s`, with short dips merged."""
    fast = np.flatnonzero(speed >= SPRINT_MS)
    if len(fast) == 0:
        return 0
    spells = np.split(fast, np.flatnonzero(np.diff(fast) > merge_s * hz) + 1)
    return sum(1 for s in spells if (s[-1] - s[0] + 1) / hz >= min_s)


def physical_summary(md: MatchData, kin: Kinematics) -> dict[str, dict[str, float]]:
    """Distance, high-intensity distance, sprints and top speed per player."""
    dt = 1.0 / md.hz
    out = {}
    for i, pid in enumerate(md.ids):
        s = kin.speed[:, i]
        out[pid] = {
            "distance_km": round(float(s.sum() * dt / 1000.0), 2),
            "high_intensity_km": round(float(s[s >= HIGH_INTENSITY_MS].sum() * dt / 1000.0), 2),
            "sprints": count_sprints(s, md.hz),
            "top_speed_kmh": round(float(s.max() * 3.6), 1),
        }
    return out

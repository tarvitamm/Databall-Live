"""Smoothed velocity, speed and acceleration from 10 Hz positions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import savgol_filter

from .match import MatchData

SPRINT_MS = 25.2 / 3.6        # sprint threshold, 25.2 km/h
HIGH_INTENSITY_MS = 19.8 / 3.6


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
    return Kinematics(vel=vel, speed=speed, accel=accel, ball_speed=np.linalg.norm(ball_v, axis=1))


def physical_summary(md: MatchData, kin: Kinematics) -> dict[str, dict[str, float]]:
    """Distance, high-intensity distance, sprints and top speed per player."""
    dt = 1.0 / md.hz
    out = {}
    for i, pid in enumerate(md.ids):
        s = kin.speed[:, i]
        sprinting = s >= SPRINT_MS
        starts = np.flatnonzero(sprinting[1:] & ~sprinting[:-1])
        out[pid] = {
            "distance_km": round(float(s.sum() * dt / 1000.0), 2),
            "high_intensity_km": round(float(s[s >= HIGH_INTENSITY_MS].sum() * dt / 1000.0), 2),
            "sprints": int(len(starts)),
            "top_speed_kmh": round(float(s.max() * 3.6), 1),
        }
    return out

"""Pitch geometry and the simulator's value models. The team frame mirrors coordinates so a team attacks
towards x = 105.
"""

from __future__ import annotations

import math

import numpy as np

LENGTH = 105.0
WIDTH = 68.0
HALF_X = LENGTH / 2
HALF_Y = WIDTH / 2
GOAL_HALF_WIDTH = 3.66
GOAL_HEIGHT = 2.44
BOX_DEPTH = 16.5
BOX_HALF_WIDTH = 20.16


def attack_sign(team: int, period: int) -> int:
    """+1 if `team` (0 home, 1 away) attacks towards x = LENGTH in `period`."""
    sign = 1 if team == 0 else -1
    return sign if period == 1 else -sign


def to_team_frame(p: np.ndarray, sign: int) -> np.ndarray:
    """Stadium frame to team frame (and back: the mapping is its own inverse)."""
    if sign == 1:
        return np.asarray(p, dtype=float)
    q = np.array(p, dtype=float, copy=True)
    q[..., 0] = LENGTH - q[..., 0]
    q[..., 1] = WIDTH - q[..., 1]
    return q


def goal_point(sign: int) -> np.ndarray:
    """Centre of the goal a team attacks, stadium frame."""
    return np.array([LENGTH if sign == 1 else 0.0, HALF_Y])


def goal_angle(p_tf: np.ndarray) -> float:
    """Angle in radians subtended by the goal mouth from a team-frame position."""
    dx = max(LENGTH - float(p_tf[0]), 0.01)
    a1 = math.atan2(HALF_Y + GOAL_HALF_WIDTH - float(p_tf[1]), dx)
    a2 = math.atan2(HALF_Y - GOAL_HALF_WIDTH - float(p_tf[1]), dx)
    return abs(a1 - a2)


def xg_true(p_tf: np.ndarray, pressure: float, header: bool = False) -> float:
    """The simulator's hidden scoring chance. Calibrated so a penalty-spot shot is about 0.17,
    a 6-yard-box shot about 0.45 and a central 25 m shot about 0.03."""
    d = math.hypot(LENGTH - float(p_tf[0]), HALF_Y - float(p_tf[1]))
    logit = -1.29 + 1.27 * goal_angle(p_tf) - 0.102 * d
    xg = 1.0 / (1.0 + math.exp(-logit))
    xg *= 1.0 - 0.35 * pressure
    if header:
        xg *= 0.6
    return xg


def threat(p_tf: np.ndarray) -> np.ndarray | float:
    """Smooth expected-threat surface in the team frame: low at home, high near the opponent goal."""
    p = np.asarray(p_tf, dtype=float)
    x, y = p[..., 0], p[..., 1]
    gx = np.exp(-((LENGTH - x) ** 2) / (2 * 20.0**2))
    gy = np.exp(-((y - HALF_Y) ** 2) / (2 * 15.0**2))
    v = 0.005 + 0.16 * gx * (0.3 + 0.7 * gy)
    return float(v) if np.ndim(v) == 0 else v


def clamp_to_pitch(p: np.ndarray, margin: float = 0.3) -> np.ndarray:
    q = np.array(p, dtype=float, copy=True)
    q[..., 0] = np.clip(q[..., 0], margin, LENGTH - margin)
    q[..., 1] = np.clip(q[..., 1], margin, WIDTH - margin)
    return q


def in_play(x: float, y: float) -> bool:
    return 0.0 <= x <= LENGTH and 0.0 <= y <= WIDTH

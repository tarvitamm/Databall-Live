"""Zone value and a time-to-intercept pitch-control model."""

from __future__ import annotations

import numpy as np

LENGTH, WIDTH = 105.0, 68.0
CELL = 2.0
GX = np.arange(CELL / 2, LENGTH, CELL)        # 53 cell centres along x
GY = np.arange(CELL / 2, WIDTH, CELL)         # 34 along y
CELLS = np.stack(np.meshgrid(GX, GY), axis=-1)  # (34, 53, 2)

REACTION_S = 0.7
VMAX = 7.0
SIGMA_S = 0.45


def zone_value(xy_team_frame: np.ndarray) -> np.ndarray:
    """Value of having the ball at a point, team frame (attacking towards x = 105). Roughly the chance the
    possession ends in a goal: near zero at home, about 0.25 in front of goal."""
    p = np.asarray(xy_team_frame, dtype=float)
    x, y = p[..., 0], p[..., 1]
    near_goal = np.exp(-((LENGTH - x) ** 2) / (2 * 14.0**2)) * np.exp(-((y - WIDTH / 2) ** 2) / (2 * 11.0**2))
    return 0.004 + 0.03 * (x / LENGTH) + 0.22 * near_goal


VALUE_GRID = zone_value(CELLS)  # (34, 53), team frame


def arrival_times(pos: np.ndarray, vel: np.ndarray, cells: np.ndarray = CELLS) -> np.ndarray:
    """Earliest time any of the given players reaches each cell. pos, vel: (P, 2)."""
    start = pos + vel * REACTION_S
    d = np.linalg.norm(cells[None, ...] - start[:, None, None, :], axis=-1)
    return (REACTION_S + d / VMAX).min(axis=0)


def pitch_control(att_pos: np.ndarray, att_vel: np.ndarray, def_pos: np.ndarray, def_vel: np.ndarray,
                  cells: np.ndarray = CELLS) -> np.ndarray:
    """Probability the attacking team controls each cell, stadium frame grid (34, 53)."""
    ok_a = ~np.isnan(att_pos[:, 0])
    ok_d = ~np.isnan(def_pos[:, 0])
    t_att = arrival_times(att_pos[ok_a], att_vel[ok_a], cells)
    t_def = arrival_times(def_pos[ok_d], def_vel[ok_d], cells)
    k = np.pi / np.sqrt(3.0) / SIGMA_S
    return 1.0 / (1.0 + np.exp(-k * (t_def - t_att)))


def value_grid_for(sign: int) -> np.ndarray:
    """VALUE_GRID laid out in the stadium frame for a team attacking with `sign`."""
    return VALUE_GRID if sign == 1 else VALUE_GRID[::-1, ::-1]


def controlled_value(control: np.ndarray, sign: int, mask: np.ndarray | None = None) -> float:
    """Sum of zone value the attacking team controls, optionally inside a boolean cell mask."""
    v = control * value_grid_for(sign)
    return float(v[mask].sum() if mask is not None else v.sum())


def disc_mask(centre: np.ndarray, radius: float) -> np.ndarray:
    return np.linalg.norm(CELLS - np.asarray(centre)[None, None, :], axis=-1) <= radius

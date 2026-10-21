"""Team shape per frame, in each team's own frame (x is metres from its own goal line)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .match import MatchData


@dataclass
class Shape:
    def_line: np.ndarray      # (N, 2) mean x of the deepest four outfield players, per team
    mid_line: np.ndarray      # (N, 2) mean x of the next four
    gap: np.ndarray           # (N, 2) mid_line - def_line
    width: np.ndarray         # (N, 2) lateral spread of outfield players
    length: np.ndarray        # (N, 2) deepest to highest outfield player
    centroid: np.ndarray      # (N, 2, 2) outfield centroid, team frame
    opp_line_in_own_frame: np.ndarray  # (N, 2) the opponents' defensive line, in this team's frame


def compute_shape(md: MatchData) -> Shape:
    n = len(md.t)
    def_line = np.zeros((n, 2))
    mid_line = np.zeros((n, 2))
    width = np.zeros((n, 2))
    length = np.zeros((n, 2))
    centroid = np.zeros((n, 2, 2))
    for team in (0, 1):
        out = md.outfield(team)
        tf = md.to_team_frame(md.pos[:, out, :], team)
        xs = np.sort(tf[:, :, 0], axis=1)
        def_line[:, team] = xs[:, :4].mean(axis=1)
        mid_line[:, team] = xs[:, 4:8].mean(axis=1)
        width[:, team] = tf[:, :, 1].max(axis=1) - tf[:, :, 1].min(axis=1)
        length[:, team] = xs[:, -1] - xs[:, 0]
        centroid[:, team] = tf.mean(axis=1)
    opp_line = 105.0 - def_line[:, ::-1]
    return Shape(def_line=def_line, mid_line=mid_line, gap=mid_line - def_line, width=width, length=length,
                 centroid=centroid, opp_line_in_own_frame=opp_line)

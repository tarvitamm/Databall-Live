"""Ball-in-play spells from events and the ball carrier from tracking."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .match import MatchData

CARRY_RADIUS = 1.3
STOPS = {"out_of_play", "foul", "goal", "half_end"}


@dataclass
class Possession:
    in_play: np.ndarray       # (N,) bool
    carrier: np.ndarray       # (N,) player index or -1
    team: np.ndarray          # (N,) team in possession or -1 when dead
    spells: list[tuple[int, int, int]]  # (team, first frame, last frame), in play only


def compute_possession(md: MatchData) -> Possession:
    n = len(md.t)
    in_play = np.ones(n, dtype=bool)
    for period in (1, 2):
        evs = sorted((e for e in md.events if e["period"] == period), key=lambda e: e["t"])
        dead_from = None
        for e in evs:
            stops = e["type"] in STOPS or (e["type"] == "pass" and e.get("outcome") == "offside")
            restarts = e.get("set_piece") is not None or e["type"] == "kick_off"
            if restarts and dead_from is not None:
                _mark_dead(md, in_play, period, dead_from, e["t"])
                dead_from = None
            if stops and dead_from is None:
                dead_from = e["t"]
        if dead_from is not None:
            _mark_dead(md, in_play, period, dead_from, np.inf)
        first = np.flatnonzero(md.period == period)[0]
        in_play[first] = False

    d = np.linalg.norm(md.pos - md.ball[:, None, :2], axis=2)
    d = np.where(np.isnan(d), np.inf, d)
    nearest = np.argmin(d, axis=1)
    close = (d[np.arange(n), nearest] < CARRY_RADIUS) & (md.ball[:, 2] < 1.2) & in_play
    raw = np.where(close, nearest, -1)
    # require two touching frames in a row
    same_prev = np.r_[False, (raw[1:] == raw[:-1]) & (raw[1:] >= 0)]
    same_next = np.r_[(raw[:-1] == raw[1:]) & (raw[:-1] >= 0), False]
    carrier = np.where(same_prev | same_next, raw, -1)

    team = np.full(n, -1)
    last = -1
    for k in range(n):
        if not in_play[k]:
            last = -1
        elif carrier[k] >= 0:
            last = int(md.team[carrier[k]])
        team[k] = last

    spells = []
    k = 0
    while k < n:
        if team[k] < 0:
            k += 1
            continue
        j = k
        while j + 1 < n and team[j + 1] == team[k] and md.period[j + 1] == md.period[k]:
            j += 1
        spells.append((int(team[k]), k, j))
        k = j + 1
    return Possession(in_play=in_play, carrier=carrier, team=team, spells=spells)


def _mark_dead(md: MatchData, in_play: np.ndarray, period: int, t0: float, t1: float) -> None:
    mask = (md.period == period) & (md.t >= t0) & (md.t < t1)
    in_play[mask] = False

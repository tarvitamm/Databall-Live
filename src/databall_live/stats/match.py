"""Load a stored match into arrays. Reads provider data only, never the hidden truth."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..contracts import MatchMetadata

LENGTH, WIDTH = 105.0, 68.0


@dataclass
class MatchData:
    meta: MatchMetadata
    events: list[dict]
    t: np.ndarray            # (N,) match clock seconds
    period: np.ndarray       # (N,) 1 or 2
    ball: np.ndarray         # (N, 3)
    pos: np.ndarray          # (N, P, 2) players in lineup order, home first
    ids: list[str]
    team: np.ndarray         # (P,) 0 home, 1 away
    positions: list[str]     # lineup position per player, e.g. "LW"
    hz: int
    signs: dict[tuple[int, int], int] = field(default_factory=dict)  # (team, period) -> +1 attacks to x=105

    @property
    def codes(self) -> tuple[str, str]:
        return self.meta.home.code, self.meta.away.code

    def team_index(self, code: str) -> int:
        return 0 if code == self.meta.home.code else 1

    def player_index(self, pid: str) -> int:
        return self.ids.index(pid)

    def frame_at(self, period: int, t: float) -> int:
        """Index of the frame at match clock `t` in `period` (clamped to that period)."""
        idx = np.flatnonzero(self.period == period)
        k = int(np.searchsorted(self.t[idx], t))
        return int(idx[min(max(k, 0), len(idx) - 1)])

    def sign(self, team: int, period: int) -> int:
        return self.signs[(team, period)]

    def sign_per_frame(self, team: int) -> np.ndarray:
        return np.where(self.period == 1, self.signs[(team, 1)], self.signs[(team, 2)])

    def to_team_frame(self, xy: np.ndarray, team: int, frames: np.ndarray | None = None) -> np.ndarray:
        """Mirror coordinates so `team` attacks towards x = 105. `xy` has the frame axis first."""
        sign = self.sign_per_frame(team) if frames is None else self.sign_per_frame(team)[frames]
        out = np.array(xy, dtype=float, copy=True)
        flip = sign == -1
        out[flip, ..., 0] = LENGTH - out[flip, ..., 0]
        out[flip, ..., 1] = WIDTH - out[flip, ..., 1]
        return out

    def members(self, team: int) -> np.ndarray:
        return np.flatnonzero(self.team == team)

    def keeper(self, team: int) -> int:
        return int(next(i for i in self.members(team) if self.positions[i] == "GK"))

    def outfield(self, team: int) -> np.ndarray:
        gk = self.keeper(team)
        return np.array([i for i in self.members(team) if i != gk])


def load_match(folder: str | Path) -> MatchData:
    folder = Path(folder)
    meta = MatchMetadata.model_validate_json((folder / "metadata.json").read_text())
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines() if line]
    ids = [p.id for p in meta.home.lineup] + [p.id for p in meta.away.lineup]
    positions = [p.position for p in meta.home.lineup] + [p.position for p in meta.away.lineup]
    team = np.array([0] * len(meta.home.lineup) + [1] * len(meta.away.lineup))

    ts, periods, balls, rows = [], [], [], []
    with (folder / "tracking.jsonl").open() as f:
        for line in f:
            fr = json.loads(line)
            ts.append(fr["t"])
            periods.append(fr["period"])
            balls.append(fr["ball"])
            players = fr["players"]
            rows.append([players.get(pid, (np.nan, np.nan)) for pid in ids])
    md = MatchData(meta=meta, events=events, t=np.array(ts), period=np.array(periods, dtype=int),
                   ball=np.array(balls, dtype=float), pos=np.array(rows, dtype=float), ids=ids, team=team,
                   positions=positions, hz=meta.hz)
    for period in (1, 2):
        first = int(np.flatnonzero(md.period == period)[0])
        for tm in (0, 1):
            mean_x = float(np.nanmean(md.pos[first, md.team == tm, 0]))
            md.signs[(tm, period)] = 1 if mean_x < LENGTH / 2 else -1
    return md

"""Off-ball runs, the defenders they drag and the space that opens behind them."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..contracts import Evidence, Pattern
from .kinematics import Kinematics
from .match import MatchData
from .possession import Possession
from .shape import Shape
from .value import controlled_value, disc_mask, pitch_control

MOVE_SPEED = 3.0         # m/s, any purposeful off-ball movement
MIN_MOVE_S = 1.0
FORWARD_RUN_SPEED = 5.0  # m/s peak, for runs forward or in behind
MIN_FORWARD_S = 1.5
SPACE_USED_MIN = 0.15    # rise in the share of the zone's value teammates control
RELATIVE_MIN_M = 4.0     # the run must beat the team's own shift by this much
FOLLOW_START_M = 12.0
FOLLOW_KEEP_M = 6.5     # mean distance the marker keeps over the second half of the run
DRAG_MIN_M = 6.0
ZONE_RADIUS_M = 8.0

ROLE = {"GK": "GK", "RCB": "CB", "LCB": "CB", "RB": "FB", "LB": "FB", "DM": "DM", "RDM": "DM", "LDM": "DM",
        "RCM": "CM", "LCM": "CM", "AM": "AM", "RM": "WM", "LM": "WM", "RW": "W", "LW": "W", "ST": "ST",
        "RS": "ST", "LS": "ST"}


@dataclass
class DetectedRun:
    player: int
    team: int
    period: int
    f0: int
    f1: int
    kind: str
    received: bool
    follower: int | None
    follow_score: float
    defender_displacement: float
    max_speed: float
    distance: float
    space_gain: float | None = None
    beneficiary: int | None = None   # teammate who attacked the vacated space
    served: bool = False             # the ball was played into that space

    @property
    def dragging(self) -> bool:
        """A marker followed the run well out of position and the runner was not passed to."""
        return self.follower is not None and not self.received and self.defender_displacement >= DRAG_MIN_M

    @property
    def decoy(self) -> bool:
        """A dragging run whose vacated space a teammate then used, or that clearly opened space."""
        return self.dragging and (self.beneficiary is not None or (self.space_gain or 0.0) >= SPACE_USED_MIN)


def _segments(mask: np.ndarray, period: np.ndarray, max_gap: int = 2) -> list[tuple[int, int]]:
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    segs = []
    start = prev = idx[0]
    for k in idx[1:]:
        if k - prev > max_gap + 1 or period[k] != period[prev]:
            segs.append((start, prev))
            start = k
        prev = k
    segs.append((start, prev))
    return segs


def detect_runs(md: MatchData, kin: Kinematics, poss: Possession, shape: Shape) -> list[DetectedRun]:
    runs: list[DetectedRun] = []
    passes = [e for e in md.events if e["type"] == "pass" and e.get("outcome") == "complete"]
    for team in (0, 1):
        opp = md.outfield(1 - team)
        for i in md.outfield(team):
            mask = (poss.team == team) & poss.in_play & (poss.carrier != i) & (kin.speed[:, i] >= MOVE_SPEED)
            for a, b in _segments(mask, md.period):
                if (b - a + 1) / md.hz < MIN_MOVE_S:
                    continue
                run = _classify(md, kin, shape, team, i, a, b)
                if run is None:
                    continue
                t_a, t_b = md.t[a], md.t[b]
                run.received = any(e["recipient"] == md.ids[i] and e["period"] == run.period
                                   and t_a <= e["t"] <= t_b + 2.0 for e in passes)
                _find_follower(md, kin, run, opp)
                runs.append(run)
    return runs


def _classify(md: MatchData, kin: Kinematics, shape: Shape, team: int, i: int, a: int, b: int) -> DetectedRun | None:
    frames = np.array([a, b])
    p = md.to_team_frame(md.pos[frames, i], team, frames=frames)
    team_shift = shape.centroid[b, team] - shape.centroid[a, team]
    rel = (p[1] - p[0]) - team_shift
    if np.linalg.norm(rel) < RELATIVE_MIN_M:
        return None
    dx = p[1, 0] - p[0, 0]
    role = ROLE.get(md.positions[i], "CM")
    opp_line = shape.opp_line_in_own_frame[b, team]
    seg = kin.speed[a:b + 1, i]
    duration = (b - a + 1) / md.hz
    forward_ok = seg.max() >= FORWARD_RUN_SPEED and duration >= MIN_FORWARD_S
    if role in ("FB", "WM") and dx >= 6.0 and abs(p[1, 1] - 34.0) >= 18.0 and forward_ok:
        kind = "overlap"
    elif dx >= 5.0 and p[1, 0] >= opp_line - 3.0 and forward_ok:
        kind = "in_behind"
    elif dx <= -4.0 and role in ("ST", "AM", "W"):
        kind = "checking"
    elif dx >= 6.0 and forward_ok:
        kind = "forward"
    else:
        return None
    return DetectedRun(player=i, team=team, period=int(md.period[a]), f0=a, f1=b, kind=kind, received=False,
                       follower=None, follow_score=0.0, defender_displacement=0.0, max_speed=float(seg.max()),
                       distance=float(seg.sum() / md.hz))


def _find_follower(md: MatchData, kin: Kinematics, run: DetectedRun, opp: np.ndarray) -> None:
    a, b, i = run.f0, run.f1, run.player
    runner = md.pos[a:b + 1, i]
    v_run = kin.vel[a:b + 1, i]
    run_disp = max(float(np.linalg.norm(runner[-1] - runner[0])), 1e-6)
    best = (0.0, None, 0.0)
    for k in opp:
        if np.linalg.norm(md.pos[a, k] - md.pos[a, i]) > FOLLOW_START_M:
            continue
        d = np.linalg.norm(md.pos[a:b + 1, k] - runner, axis=1)
        # markers may close in, so judge the second half
        keep = float(d[len(d) // 2:].mean())
        v_def = kin.vel[a:b + 1, k]
        moving = (np.linalg.norm(v_run, axis=1) > 1.0) & (np.linalg.norm(v_def, axis=1) > 1.0)
        if moving.sum() < 3:
            continue
        cos = np.einsum("ij,ij->i", v_run[moving], v_def[moving]) / (
            np.linalg.norm(v_run[moving], axis=1) * np.linalg.norm(v_def[moving], axis=1))
        cos_mean = float(cos.mean())
        disp = float(np.linalg.norm(md.pos[b, k] - md.pos[a, k]))
        ratio = disp / run_disp
        score = max(cos_mean, 0.0) * min(1.0, ratio) * max(0.0, 1.0 - keep / 10.0)
        if keep <= FOLLOW_KEEP_M and cos_mean >= 0.6 and ratio >= 0.5 and disp >= 4.0 and score > best[0]:
            best = (score, int(k), disp)
    run.follow_score, run.follower, run.defender_displacement = best[0], best[1], best[2]


def measure_space(md: MatchData, kin: Kinematics, run: DetectedRun) -> None:
    """Value of the space teammates control where the dragged defender started, before vs after the run."""
    if run.follower is None:
        return
    team = run.team
    sign = md.sign(team, run.period)
    a = run.f0
    last = int(np.flatnonzero(md.period == run.period)[-1])
    b = min(run.f1 + md.hz, last)
    centre = md.pos[a, run.follower]
    mask = disc_mask(centre, ZONE_RADIUS_M)
    att, dfn = md.members(team), md.members(1 - team)
    before = pitch_control(md.pos[a, att], kin.vel[a, att], md.pos[a, dfn], kin.vel[a, dfn])
    after = pitch_control(md.pos[b, att], kin.vel[b, att], md.pos[b, dfn], kin.vel[b, dfn])
    total = controlled_value(np.ones_like(after), sign, mask)
    run.space_gain = (controlled_value(after, sign, mask) - controlled_value(before, sign, mask)) / max(total, 1e-9)
    # first teammate within 5 m of the vacated spot
    last_f = min(run.f1 + 3 * md.hz, last)
    window = slice(run.f0 + md.hz // 2, last_f + 1)
    first_hit = None
    for j in md.members(team):
        if j == run.player or j == md.keeper(team):
            continue
        near = np.flatnonzero(np.linalg.norm(md.pos[window, j] - centre, axis=1) <= 5.0)
        if len(near) and (first_hit is None or near[0] < first_hit[0]):
            first_hit = (int(near[0]), int(j))
    if first_hit is not None:
        run.beneficiary = first_hit[1]
    # a pass or carry into the vacated zone
    t_start, t_end = md.t[run.f0], md.t[run.f1]
    for e in md.events:
        if e["period"] != run.period or not (t_start < e["t"] <= t_end + 5.0) or e.get("team") != md.codes[team]:
            continue
        if e["type"] == "pass" and e.get("outcome") == "complete" and e.get("end") is not None:
            into_zone = np.linalg.norm(np.array(e["end"]) - centre) <= ZONE_RADIUS_M + 4.0
            if into_zone and e["recipient"] != md.ids[run.player]:
                run.beneficiary = md.player_index(e["recipient"])
                run.served = True
                return
        if e["type"] == "carry" and e.get("end") is not None and e["player"] != md.ids[run.player]:
            if np.linalg.norm(np.array(e["end"]) - centre) <= ZONE_RADIUS_M:
                run.beneficiary = md.player_index(e["player"])
                run.served = True
                return


PATTERN_TYPE = {"in_behind": "run_in_behind", "checking": "checking_run", "overlap": "overlap_run",
                "forward": "forward_run"}


def run_patterns(md: MatchData, runs: list[DetectedRun], start_id: int = 1) -> list[Pattern]:
    out: list[Pattern] = []
    n = start_id
    for r in runs:
        t0, t1 = float(md.t[r.f0]), float(md.t[r.f1])
        measures: dict[str, float | str] = {"run_speed_kmh": round(r.max_speed * 3.6, 1),
                                            "distance_m": round(r.distance, 1), "received": str(r.received).lower()}
        affected = []
        if r.follower is not None:
            affected = [md.ids[r.follower]]
            measures["defender_displacement_m"] = round(r.defender_displacement, 1)
            measures["follow_score"] = round(r.follow_score, 2)
        base = Pattern(id=f"pt_{n}", match=md.meta.match, type=PATTERN_TYPE[r.kind], period=r.period, t_start=t0,
                       t_end=t1, actor=md.ids[r.player], team=md.codes[r.team], affected=affected, measures=measures,
                       evidence=Evidence(window=(t0, t1)), significance=0.15 + (0.1 if r.kind == "in_behind" else 0.0))
        out.append(base)
        n += 1
        if r.decoy:
            m = dict(measures)
            if r.space_gain is not None:
                m["space_value_gain"] = round(r.space_gain, 3)
            if r.beneficiary is not None:
                m["beneficiary"] = md.ids[r.beneficiary]
                m["space_served"] = str(r.served).lower()
            sig = 0.35 + min(0.3, max(0.0, r.space_gain or 0.0)) + (0.1 if r.beneficiary is not None else 0.0) \
                + (0.2 if r.served else 0.0)
            out.append(Pattern(id=f"pt_{n}", match=md.meta.match, type="decoy_run", period=r.period, t_start=t0,
                               t_end=t1, actor=md.ids[r.player], team=md.codes[r.team], affected=affected,
                               measures=m, evidence=Evidence(patterns=[base.id], window=(t0, t1 + 5.0)),
                               significance=round(min(sig, 1.0), 2)))
            n += 1
    return out

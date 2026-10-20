"""Pass and shot metrics, linked to tracking at the moment of release."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .kinematics import Kinematics
from .match import LENGTH, WIDTH, MatchData
from .shape import Shape

MODELS = Path(__file__).parent / "models"
GOAL_HALF = 3.66


@dataclass
class PassMetrics:
    event: str
    team: int
    passer: int
    frame: int
    complete: bool
    distance_m: float
    speed_kmh: float
    progressive: bool
    lines_broken: int
    under_pressure: bool
    passer_space_m: float
    lane_defenders: int
    target_space_m: float
    lofted: bool
    forward_m: float
    difficulty: float | None = None


@dataclass
class ShotMetrics:
    event: str
    team: int
    shooter: int
    frame: int
    outcome: str
    distance_m: float
    angle_rad: float
    header: bool
    defenders_in_cone: int
    pressure_m: float
    speed_kmh: float
    xg: float | None = None


def _segment_distance(a: np.ndarray, b: np.ndarray, p: np.ndarray) -> np.ndarray:
    ab = b - a
    denom = max(float(ab @ ab), 1e-9)
    s = np.clip(((p - a) @ ab) / denom, 0.0, 1.0)
    return np.linalg.norm(a + s[:, None] * ab - p, axis=1)


def _peak_kmh(kin: Kinematics, window: slice) -> float:
    v = kin.ball_speed[window]
    return round(float(np.nanmax(v)) * 3.6, 1) if np.isfinite(v).any() else 0.0


def _tf(md: MatchData, xy, team: int, period: int) -> np.ndarray:
    p = np.asarray(xy, dtype=float)
    return p if md.sign(team, period) == 1 else np.array([LENGTH - p[0], WIDTH - p[1]])


def pass_metrics(md: MatchData, kin: Kinematics, shape: Shape) -> list[PassMetrics]:
    out = []
    for e in md.events:
        if e["type"] != "pass" or e.get("outcome") == "offside" or e.get("set_piece") == "throw_in":
            continue
        team, period = md.team_index(e["team"]), e["period"]
        f = md.frame_at(period, e["t"])
        start, end = np.array(e["start"]), np.array(e["end"])
        s_tf, e_tf = _tf(md, start, team, period), _tf(md, end, team, period)
        opp = md.outfield(1 - team)
        opp_pos = md.pos[f, opp]
        passer = md.player_index(e["player"])
        opp_lines = [LENGTH - shape.def_line[f, 1 - team], LENGTH - shape.mid_line[f, 1 - team]]
        complete = e.get("outcome") == "complete"
        window = slice(f, min(f + 6, len(md.t)))
        out.append(PassMetrics(
            event=e["id"], team=team, passer=passer, frame=f, complete=complete,
            distance_m=round(float(np.linalg.norm(end - start)), 1),
            speed_kmh=_peak_kmh(kin, window),
            progressive=bool(e_tf[0] - s_tf[0] >= 10.0 or (e_tf[0] > LENGTH - 16.5 and abs(e_tf[1] - 34) < 20.16)),
            lines_broken=int(sum(s_tf[0] < x < e_tf[0] for x in opp_lines)) if complete else 0,
            under_pressure=bool(np.min(np.linalg.norm(opp_pos - md.pos[f, passer], axis=1)) < 3.0),
            passer_space_m=round(float(np.min(np.linalg.norm(opp_pos - md.pos[f, passer], axis=1))), 1),
            lane_defenders=int(np.sum(_segment_distance(start, end, opp_pos) < 2.0)),
            target_space_m=round(float(np.min(np.linalg.norm(opp_pos - end, axis=1))), 1),
            lofted=e.get("height") == "high",
            forward_m=round(float(e_tf[0] - s_tf[0]), 1),
        ))
    return out


def shot_metrics(md: MatchData, kin: Kinematics) -> list[ShotMetrics]:
    out = []
    for e in md.events:
        if e["type"] != "shot":
            continue
        team, period = md.team_index(e["team"]), e["period"]
        f = md.frame_at(period, e["t"])
        p = _tf(md, e["start"], team, period)
        dx, dy = LENGTH - p[0], 34.0 - p[1]
        angle = abs(math.atan2(dy + GOAL_HALF, max(dx, 0.01)) - math.atan2(dy - GOAL_HALF, max(dx, 0.01)))
        opp = md.outfield(1 - team)
        opp_tf = np.array([_tf(md, q, team, period) for q in md.pos[f, opp]])
        in_cone = 0
        for q in opp_tf:
            if q[0] <= p[0]:
                continue
            a = math.atan2(q[1] - p[1], q[0] - p[0])
            lo = math.atan2(34.0 - GOAL_HALF - p[1], dx)
            hi = math.atan2(34.0 + GOAL_HALF - p[1], dx)
            in_cone += int(lo - 0.05 <= a <= hi + 0.05)
        shooter = md.player_index(e["player"])
        window = slice(f, min(f + 4, len(md.t)))
        out.append(ShotMetrics(
            event=e["id"], team=team, shooter=shooter, frame=f, outcome=e.get("outcome", ""),
            distance_m=round(float(math.hypot(dx, dy)), 1), angle_rad=round(angle, 3),
            header=e.get("body_part") == "head", defenders_in_cone=in_cone,
            pressure_m=round(float(np.min(np.linalg.norm(md.pos[f, opp] - md.pos[f, shooter], axis=1))), 1),
            speed_kmh=_peak_kmh(kin, window),
        ))
    return out


def pass_features(p: PassMetrics) -> list[float]:
    return [p.distance_m / 20.0, p.forward_m / 20.0, min(p.passer_space_m, 10.0) / 5.0, p.lane_defenders,
            float(p.lofted)]


def shot_features(s: ShotMetrics) -> list[float]:
    return [s.distance_m / 10.0, s.angle_rad, float(s.header), s.defenders_in_cone, min(s.pressure_m, 5.0) / 5.0]


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 50) -> np.ndarray:
    """Newton-Raphson logistic regression with an L2 penalty. Returns weights with the intercept first."""
    x = np.column_stack([np.ones(len(x)), x])
    w = np.zeros(x.shape[1])
    reg = np.eye(len(w)) * l2
    reg[0, 0] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-x @ w))
        grad = x.T @ (p - y) + reg @ w
        hess = (x * (p * (1 - p))[:, None]).T @ x + reg
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return w


def predict(w: list[float] | np.ndarray, features: list[float]) -> float:
    z = float(w[0] + np.dot(w[1:], features))
    return 1.0 / (1.0 + math.exp(-z))


def load_model(name: str) -> list[float] | None:
    path = MODELS / f"{name}.json"
    return json.loads(path.read_text())["weights"] if path.exists() else None


def score(passes: list[PassMetrics], shots: list[ShotMetrics]) -> None:
    xpass, xg = load_model("xpass"), load_model("xg")
    if xpass is not None:
        for p in passes:
            p.difficulty = round(10.0 * (1.0 - predict(xpass, pass_features(p))), 1)
    if xg is not None:
        for s in shots:
            s.xg = round(predict(xg, shot_features(s)), 3)

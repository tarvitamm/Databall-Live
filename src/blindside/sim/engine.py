"""Agent-based match engine: 22 players and a ball stepped at 10 Hz.

Events are stamped when they start (a pass at release). Off-ball choices such as runs, decoys and marking
are recorded in the hidden truth.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from ..contracts import RunTruth, TacticChange, TacticState, Truth
from .clubs import Club, Player
from .pitch import (
    BOX_DEPTH,
    BOX_HALF_WIDTH,
    GOAL_HALF_WIDTH,
    HALF_X,
    HALF_Y,
    LENGTH,
    WIDTH,
    attack_sign,
    in_play,
    threat,
    to_team_frame,
    xg_true,
)
from .tactics import FORMATIONS, ScriptedChange, Tactics, scenario_changes

SIM_VERSION = "0.1.0"
HZ = 10
DT = 1.0 / HZ
G = 9.81
ROLL_DECEL = 2.5          # m/s2, ball rolling on grass
CONTROL_RADIUS = 1.0      # m, a player can play the ball inside this distance
TACKLE_RANGE = 1.3        # m
PRESSURE_RANGE = 4.0      # m
PERIOD_BASE = {1: 0.0, 2: 45 * 60.0}
SHOT_BIAS = 0.6          # how readily players shoot, relative to the chance's xG
SHOT_MIN_XG = 0.07       # players ignore shooting chances below this

# off-ball run starts per second of possession, per role, at run_rate 0.5
RUN_BASE = {"ST": 0.025, "W": 0.022, "AM": 0.015, "WM": 0.012, "CM": 0.007, "FB": 0.008}
ATTACKING_ROLES = {"ST", "W", "AM", "WM"}

EventSink = Callable[[dict], None]
FrameSink = Callable[[dict], None]


@dataclass
class Run:
    truth_index: int
    target: np.ndarray            # stadium frame
    t_end: float
    follower: int | None


@dataclass
class PassInFlight:
    passer: int
    receiver: int
    start: np.ndarray
    release_t: float
    height: str
    set_piece: str | None
    body_part: str


@dataclass
class ShotInFlight:
    shooter: int
    start: np.ndarray
    release_t: float
    outcome: str                  # goal, saved, blocked, off_target
    body_part: str
    blocker: int | None
    block_point: np.ndarray | None
    set_piece: str | None


@dataclass
class Restart:
    kind: str                     # kick_off, throw_in, corner, goal_kick, free_kick
    team: int
    spot: np.ndarray
    at: float
    taker: int


@dataclass
class MatchStats:
    possession_ticks: list[int] = field(default_factory=lambda: [0, 0])
    distance: np.ndarray = field(default_factory=lambda: np.zeros(22))
    top_speed: np.ndarray = field(default_factory=lambda: np.zeros(22))
    ball_in_play_ticks: int = 0


class MatchEngine:
    def __init__(self, home: Club, away: Club, seed: int, scenario: str = "free",
                 match_id: str | None = None, half_minutes: float = 45.0):
        self.home, self.away = home, away
        self.clubs = (home, away)
        self.seed = seed
        self.scenario = scenario
        self.match_id = match_id or f"m_{seed:04d}"
        self.half_seconds = half_minutes * 60.0
        self.rng = np.random.default_rng(seed)

        self.players: list[Player] = list(home.lineup) + list(away.lineup)
        self.ids = [p.id for p in self.players]
        self.slots = [p.slot for p in self.players]
        self.roles = [p.role for p in self.players]
        self.team = np.array([0] * 11 + [1] * 11)
        self.members = (np.arange(0, 11), np.arange(11, 22))
        self.gk = (self.slots.index("GK"), 11 + self.slots[11:].index("GK"))
        attr = lambda name: np.array([getattr(p, name) for p in self.players], dtype=float)  # noqa: E731
        self.top_speed = attr("top_speed")
        self.accel = attr("accel")
        self.stamina = attr("stamina")
        self.passing = attr("passing")
        self.vision = attr("vision")
        self.first_touch = attr("first_touch")
        self.finishing = attr("finishing")
        self.tackling = attr("tackling")
        self.dribbling = attr("dribbling")
        self.work_rate = attr("work_rate")

        self.tactics = [home.tactics, away.tactics]
        self.scripted = sorted(scenario_changes(scenario, home.code, away.code), key=lambda c: (c.period, c.t))
        self.run_mult = np.ones(22)
        self.decoy_override = np.full(22, np.nan)
        self.drain_mult = np.ones(2)

        self.pos = np.zeros((22, 2))
        self.vel = np.zeros((22, 2))
        self.energy = np.ones(22)
        self.wander = np.zeros((22, 2))

        self.ball = np.array([HALF_X, HALF_Y, 0.0])
        self.ball_vel = np.zeros(3)
        self.state = "dead"       # owned, air, dead
        self.owner = -1
        self.poss_team = 0
        self.last_touch = -1
        self.kicker = -1
        self.kick_t = -99.0
        self.pass_ctx: PassInFlight | None = None
        self.shot_ctx: ShotInFlight | None = None
        self.restart: Restart | None = None

        self.decision_t = 0.0
        self.last_decision_t = -99.0
        self.carry_dir = np.zeros(2)
        self.carry_speed = 0.0
        self.carry_start: tuple[np.ndarray, float] | None = None

        self.runs: dict[int, Run] = {}
        self.run_cooldown = np.zeros(22)
        self.follow: dict[int, int] = {}          # defender -> runner
        self.pending_exploits: list[tuple[float, int, np.ndarray, str]] = []  # (at, player, target, decoy id)
        self.control_cd = np.zeros(22)
        self.tackle_cd = np.zeros(22)
        self.engaged: set[int] = set()
        self.engaged_carrier = -1

        self.period = 1
        self.k = 0
        self.t = 0.0
        self.period_end = 0.0
        self.event_n = 0
        self.events: list[dict] = []
        self.tactic_log: list[TacticChange] = []
        self.run_log: list[RunTruth] = []
        self.fatigue_log: dict[str, list[float]] = {pid: [] for pid in self.ids}
        self.markers: list[dict] = []
        self.stats = MatchStats()
        self._on_event: EventSink = lambda e: None


    def run(self, on_event: EventSink, on_frame: FrameSink) -> Truth:
        self._on_event = on_event
        for team in (0, 1):
            self._log_tactics(team, "starting tactics")
        for period in (1, 2):
            self._start_period(period)
            while self.t < self.period_end:
                self._step()
                on_frame(self._frame())
                self.k += 1
                self.t = round(PERIOD_BASE[period] + self.k * DT, 1)
            self._emit("half_end")
        return Truth(match=self.match_id, seed=self.seed, scenario=self.scenario, tactics=self.tactic_log,
                     runs=self.run_log, fatigue=self.fatigue_log, markers=self.markers)


    def _start_period(self, period: int) -> None:
        self.period = period
        self.k = 0
        self.t = PERIOD_BASE[period]
        stoppage = self.rng.uniform(60, 180) if period == 1 else self.rng.uniform(150, 330)
        self.period_end = self.t + self.half_seconds + stoppage
        self.pass_ctx = self.shot_ctx = None
        self.runs.clear()
        self.follow.clear()
        kicking = 0 if period == 1 else 1
        self._place_for_kickoff(kicking)
        self._emit("half_start")
        self._set_restart("kick_off", kicking, np.array([HALF_X, HALF_Y]), delay=0.0)

    def _place_for_kickoff(self, kicking: int) -> None:
        for team in (0, 1):
            sign = attack_sign(team, self.period)
            form = FORMATIONS[self.clubs[team].formation]
            for i in self.members[team]:
                _, out, _ = form[self.slots[i]]
                p = np.array([min(out[0] * 0.95, HALF_X - 1.0), out[1]])
                self.pos[i] = to_team_frame(p, sign)
        self.vel[:] = 0.0


    def _step(self) -> None:
        self._apply_scripted()
        self._update_runs()
        targets, speeds = self._targets()
        self._move(targets, speeds)
        self._update_ball()
        if self.state == "owned":
            self._duels()
        if self.state == "owned":
            self._carrier_logic()
        elif self.state == "dead":
            self._dead_logic()
        if self.state == "owned":
            self._pressure_events()
            self.stats.possession_ticks[self.poss_team] += 1
        if self.state != "dead":
            self.stats.ball_in_play_ticks += 1
        self._fatigue()


    def _apply_scripted(self) -> None:
        while self.scripted and (self.scripted[0].period, self.scripted[0].t) <= (self.period, self.t):
            change: ScriptedChange = self.scripted.pop(0)
            team = 0 if change.team == self.home.code else 1
            if change.tactics:
                self.tactics[team] = self.tactics[team].with_changes(**change.tactics)
                self._log_tactics(team, change.note)
            if change.player is not None:
                i = self.ids.index(change.player)
                if change.player_run_mult is not None:
                    self.run_mult[i] = change.player_run_mult
                if change.player_decoy_share is not None:
                    self.decoy_override[i] = change.player_decoy_share
            if change.energy_drain_mult is not None:
                self.drain_mult[team] = change.energy_drain_mult
            self.markers.append({"t": self.t, "period": self.period, "team": change.team,
                                 "player": change.player, "note": change.note})

    def _log_tactics(self, team: int, note: str) -> None:
        tac: Tactics = self.tactics[team]
        self.tactic_log.append(TacticChange(t=self.t, period=self.period, team=self.clubs[team].code,
                                            tactics=TacticState(**tac.as_dict()), note=note))


    def _sign(self, team: int) -> int:
        return attack_sign(team, self.period)

    def _tf(self, p: np.ndarray, team: int) -> np.ndarray:
        return to_team_frame(p, self._sign(team))

    def _attack_dir(self, team: int) -> np.ndarray:
        return np.array([float(self._sign(team)), 0.0])

    def _offside_line(self, team: int) -> float:
        """Team-frame x of the opponents' last outfield defender (or the ball if further)."""
        opp = self.members[1 - team]
        opp_out = [i for i in opp if i != self.gk[1 - team]]
        xs = self._tf(self.pos[opp_out], team)[:, 0]
        ball_x = self._tf(self.ball[:2], team)[0]
        return max(float(xs.max()), float(ball_x), HALF_X)

    def _is_offside(self, j: int) -> bool:
        """Beyond the second-last defender and the ball, in the opponents' half."""
        team = self.team[j]
        x = self._tf(self.pos[j], team)[0]
        return bool(x > HALF_X and x > self._offside_line(team) + 0.3)

    def _pressure_on(self, i: int) -> float:
        opp = self.members[1 - self.team[i]]
        d = np.linalg.norm(self.pos[opp] - self.pos[i], axis=1)
        j = int(np.argmin(d))
        r = float(d[j])
        rel = self.pos[i] - self.pos[opp[j]]
        closing = float(np.dot(self.vel[opp[j]] - self.vel[i], rel / max(r, 1e-6)))
        return float(np.clip((PRESSURE_RANGE - r) / 3.5 + (0.15 if closing > 1.0 else 0.0), 0.0, 1.0))


    def _targets(self) -> tuple[np.ndarray, np.ndarray]:
        T = np.empty((22, 2))
        S = np.full(22, 0.3)
        self.wander += -self.wander * DT / 6.0 + self.rng.normal(0, 0.6, (22, 2)) * math.sqrt(DT)
        ball_xy = self.ball[:2]

        for team in (0, 1):
            sign = self._sign(team)
            tac: Tactics = self.tactics[team]
            in_poss = self.poss_team == team and self.state != "dead"
            form = FORMATIONS[self.clubs[team].formation]
            ball_tf = to_team_frame(ball_xy, sign)
            off_line = self._offside_line(team)
            for i in self.members[team]:
                slot = self.slots[i]
                a_in, a_out, _ = form[slot]
                if slot == "GK":
                    gx = np.clip(3.0 + 0.12 * ball_tf[0], 3.0, 16.0)
                    gy = HALF_Y + (ball_tf[1] - HALF_Y) * 0.12
                    T[i] = to_team_frame(np.array([gx, gy]), sign)
                    S[i] = 0.5
                    continue
                if in_poss:
                    bx = a_in[0]
                    by = HALF_Y + (a_in[1] - HALF_Y) * (0.8 + 0.4 * tac.width)
                    kx, ky = 0.5, 0.3
                else:
                    bx = a_out[0] + (tac.block_height - 0.5) * 26.0
                    by = a_out[1]
                    kx, ky = 0.45, 0.45
                tx = bx + kx * (ball_tf[0] - HALF_X) + self.wander[i, 0]
                ty = by + ky * (ball_tf[1] - HALF_Y) + self.wander[i, 1]
                if in_poss and self.roles[i] != "GK":
                    tx = min(tx, off_line - 0.7)
                if not in_poss and ball_tf[0] < 32.0 and self.roles[i] in ("CB", "FB", "DM", "CM", "WM"):
                    pull = 0.35 * (32.0 - ball_tf[0]) / 32.0 + 0.15
                    mx, my = 0.5 * (ball_tf[0] + 3.0), 0.5 * (ball_tf[1] + HALF_Y)
                    tx, ty = tx * (1 - pull) + mx * pull, ty * (1 - pull) + my * pull
                if not in_poss and self.roles[i] in ("CB", "FB"):
                    tx = max(tx, 5.0)
                T[i] = to_team_frame(np.array([np.clip(tx, 3.0, LENGTH - 3.0), np.clip(ty, 2.0, WIDTH - 2.0)]), sign)

        if self.state == "dead" and self.restart is not None:
            if self.restart.kind == "kick_off":
                self._kickoff_targets(T)
            T[self.restart.taker] = self.restart.spot
            S[self.restart.taker] = 0.7
            return T, S

        self._box_marking(T, S)
        for i, run in self.runs.items():
            T[i] = run.target
            S[i] = 0.95
        for d, r in self.follow.items():
            goal_side = -self._attack_dir(self.team[d]) * 1.0
            T[d] = self.pos[r] + self.vel[r] * 0.3 + goal_side
            S[d] = 0.95

        if self.state == "owned":
            self._pressing_targets(T, S)
            o = self.owner
            T[o] = self.pos[o] + self.carry_dir * 3.0
            S[o] = self.carry_speed
            # a defender in the path slows the carrier
            rel = self.pos[self.members[1 - self.team[o]]] - self.pos[o]
            dist = np.linalg.norm(rel, axis=1)
            ahead = rel @ self.carry_dir > 0.5 * dist
            if np.any((dist < 2.0) & ahead):
                S[o] = min(S[o], 0.15)
        elif self.state == "air":
            for i, (target, urgency) in self._chase_targets().items():
                T[i] = target
                S[i] = urgency
        return T, S

    def _box_marking(self, T: np.ndarray, S: np.ndarray) -> None:
        """Near their own goal, defenders pick up the most dangerous attackers goal-side."""
        team = 1 - self.poss_team
        if self._tf(self.ball[:2], team)[0] > 35.0:
            return
        sign = self._sign(team)
        own_goal = to_team_frame(np.array([0.0, HALF_Y]), sign)
        attackers = [a for a in self.members[self.poss_team]
                     if a != self.gk[self.poss_team] and a != self.owner and self._tf(self.pos[a], team)[0] < 25.0]
        attackers.sort(key=lambda a: float(np.linalg.norm(self.pos[a] - own_goal)))
        free = [d for d in self.members[team]
                if self.roles[d] in ("CB", "FB", "DM", "CM", "WM") and d not in self.follow]
        for a in attackers:
            if not free:
                break
            dists = [float(np.linalg.norm(self.pos[d] - self.pos[a])) for d in free]
            k = int(np.argmin(dists))
            if dists[k] > 12.0:
                continue
            d = free.pop(k)
            to_goal = own_goal - self.pos[a]
            T[d] = self.pos[a] + to_goal / max(float(np.linalg.norm(to_goal)), 1e-6) * 1.0
            S[d] = 0.8

    def _kickoff_targets(self, T: np.ndarray) -> None:
        for team in (0, 1):
            sign = self._sign(team)
            form = FORMATIONS[self.clubs[team].formation]
            for i in self.members[team]:
                _, out, _ = form[self.slots[i]]
                T[i] = to_team_frame(np.array([min(out[0] * 0.95, HALF_X - 1.0), out[1]]), sign)

    def _pressing_targets(self, T: np.ndarray, S: np.ndarray) -> None:
        carrier = self.owner
        team = 1 - self.team[carrier]
        tac: Tactics = self.tactics[team]
        carrier_tf_x = self._tf(self.pos[carrier], team)[0]
        defenders = [i for i in self.members[team] if i != self.gk[team] and i not in self.follow]
        d = np.linalg.norm(self.pos[defenders] - self.pos[carrier], axis=1)
        order = np.argsort(d)
        engage = carrier_tf_x <= 35.0 + 70.0 * tac.press_intensity
        trigger = 8.0 + 12.0 * tac.press_intensity
        n_press = 1 + int(round(2 * tac.press_intensity)) if engage else 0
        pressed = 0
        for idx in order:
            i = defenders[idx]
            if pressed < n_press and d[idx] < trigger:
                T[i] = self.pos[carrier] + self.vel[carrier] * 0.25 - self._attack_dir(self.team[carrier]) * 1.2
                S[i] = 0.75 + 0.25 * self.work_rate[i]
                pressed += 1
            elif pressed == 0 and d[idx] < 12.0:
                # contain: stay goal-side
                T[i] = self.pos[carrier] - self._attack_dir(self.team[carrier]) * 3.5
                S[i] = 0.7
                pressed = -1
            if pressed >= n_press or pressed == -1:
                break

    def _predict_ball(self, steps: int = 16, dt: float = 0.2) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p = self.ball.copy()
        v = self.ball_vel.copy()
        pts, ts, zs = [], [], []
        sub = int(round(dt / DT))
        for s in range(1, steps + 1):
            for _ in range(sub):
                p, v = _ball_physics(p, v)
            pts.append(p[:2].copy())
            ts.append(s * dt)
            zs.append(p[2])
        return np.array(pts), np.array(ts), np.array(zs)

    def _chase_targets(self) -> dict[int, tuple[np.ndarray, float]]:
        if self.shot_ctx is not None:
            gk = self.gk[1 - self.team[self.shot_ctx.shooter]]
            pts, ts, _ = self._predict_ball(8, 0.1)
            gk_x = self.pos[gk, 0]
            j = int(np.argmin(np.abs(pts[:, 0] - gk_x)))
            return {gk: (pts[j], 1.0)}
        pts, tb, zs = self._predict_ball()
        playable = zs < 1.8
        D = np.linalg.norm(self.pos[:, None, :] - pts[None, :, :], axis=2)
        treach = 0.25 + np.maximum(D - 0.8, 0.0) / (self.top_speed[:, None] * 0.95)
        margin = np.where(playable[None, :], tb[None, :] - treach, -9.0)
        feasible = margin >= -0.05
        can = feasible.any(axis=1)
        idx = np.where(can, feasible.argmax(axis=1), margin.argmax(axis=1))
        # earliest arrival wins
        arrival = np.where(can, tb[idx], 100.0 - margin[np.arange(22), idx])
        out: dict[int, tuple[np.ndarray, float]] = {}
        for team in (0, 1):
            members = [i for i in self.members[team] if not (i == self.kicker and self.t - self.kick_t < 0.5)]
            if not members:
                continue
            m = min(members, key=lambda i: (arrival[i], D[i, idx[i]]))
            out[m] = (pts[idx[m]], 1.0)
        if self.pass_ctx is not None:
            r = self.pass_ctx.receiver
            out[r] = (pts[idx[r]], 0.95)
        return out


    def _move(self, T: np.ndarray, S: np.ndarray) -> None:
        d = T - self.pos
        dist = np.linalg.norm(d, axis=1)
        unit = d / np.maximum(dist, 1e-6)[:, None]
        fatigue = 0.82 + 0.18 * self.energy
        vmax = self.top_speed * S * fatigue
        desired = unit * np.minimum(vmax, dist * 1.5)[:, None]
        dv = desired - self.vel
        dvn = np.linalg.norm(dv, axis=1)
        slowing = np.einsum("ij,ij->i", desired, self.vel) < np.einsum("ij,ij->i", self.vel, self.vel)
        limit = self.accel * DT * (0.85 + 0.15 * self.energy) * np.where(slowing, 1.6, 1.0)
        scale = np.minimum(1.0, limit / np.maximum(dvn, 1e-9))
        self.vel += dv * scale[:, None]
        step = self.vel * DT
        self.pos += step
        self.pos[:, 0] = np.clip(self.pos[:, 0], -1.0, LENGTH + 1.0)
        self.pos[:, 1] = np.clip(self.pos[:, 1], -1.0, WIDTH + 1.0)
        speed = np.linalg.norm(self.vel, axis=1)
        self.stats.distance += speed * DT
        self.stats.top_speed = np.maximum(self.stats.top_speed, speed)

    def _fatigue(self) -> None:
        speed = np.linalg.norm(self.vel, axis=1)
        drain = (5.0e-5 + 1.6e-5 * np.maximum(speed - 2.0, 0.0) ** 2) * (1.35 - self.stamina)
        drain *= self.drain_mult[self.team]
        self.energy = np.clip(self.energy - drain * DT, 0.3, 1.0)
        if self.k % (60 * HZ) == 0 and self.k > 0:
            for i, pid in enumerate(self.ids):
                self.fatigue_log[pid].append(round(float(self.energy[i]), 3))


    def _update_runs(self) -> None:
        for i in list(self.runs):
            run = self.runs[i]
            reached = np.linalg.norm(self.pos[i] - run.target) < 1.5
            lost = self.state == "owned" and self.team[self.owner] != self.team[i]
            if self.t >= run.t_end or reached or lost or self.owner == i:
                self._end_run(i)
        self._launch_exploits()
        if self.k % 5 != 0 or self.state != "owned":
            return
        team = self.team[self.owner]
        if self.owner == self.gk[team]:
            return
        tac: Tactics = self.tactics[team]
        ball_tf = self._tf(self.ball[:2], team)
        if ball_tf[0] < 30.0:
            return
        for i in self.members[team]:
            role = self.roles[i]
            if i == self.owner or i in self.runs or role not in RUN_BASE or self.t < self.run_cooldown[i]:
                continue
            p = RUN_BASE[role] * (tac.run_rate / 0.5) * self.run_mult[i] * 0.5
            if self.rng.random() < p:
                self._start_run(i, team, ball_tf)

    def _start_run(self, i: int, team: int, ball_tf: np.ndarray) -> None:
        tac: Tactics = self.tactics[team]
        role = self.roles[i]
        me = self._tf(self.pos[i], team)
        off_line = self._offside_line(team)
        rng = self.rng
        same_flank = abs(ball_tf[1] - me[1]) < 20.0
        if role in ("FB", "WM") and same_flank and ball_tf[0] > 40.0:
            kind = "overlap"
            side = 3.0 if me[1] < HALF_Y else WIDTH - 3.0
            tgt = np.array([min(ball_tf[0] + rng.uniform(10, 18), 100.0), side])
            dur = 5.0
        elif role == "FB":
            return  # full-backs only run to overlap
        elif role in ("ST", "AM") and rng.random() < 0.45:
            kind = "checking"
            tgt = np.array([max(off_line - rng.uniform(6, 12), ball_tf[0] - 5.0),
                            me[1] + 0.4 * (ball_tf[1] - me[1])])
            dur = 3.0
        elif role == "W" and rng.random() < 0.3:
            kind = "checking"
            tgt = np.array([max(me[0] - rng.uniform(5, 9), ball_tf[0] - 8.0), me[1] + 0.3 * (ball_tf[1] - me[1])])
            dur = 3.0
        else:
            kind = "in_behind"
            inward = (HALF_Y - me[1])
            if role == "W":
                ty = me[1] + np.sign(inward) * min(abs(inward), rng.uniform(4, 12))
            else:
                ty = me[1] + rng.uniform(-5, 5)
            tgt = np.array([min(off_line + rng.uniform(6, 14), 100.0), ty])
            dur = 4.5
        decoy_p = self.decoy_override[i] if not np.isnan(self.decoy_override[i]) else tac.decoy_share
        intent = "decoy" if rng.random() < decoy_p else "target"
        self._launch_run(i, team, kind, tgt, dur, intent)

    def _launch_run(self, i: int, team: int, kind: str, tgt: np.ndarray, dur: float, intent: str,
                    linked_to: str | None = None) -> None:
        """Start a run towards `tgt` (team frame). The nearest free defender chooses to follow or hold."""
        tgt = np.array([np.clip(tgt[0], 2.0, LENGTH - 2.0), np.clip(tgt[1], 2.0, WIDTH - 2.0)])
        # the nearest free defender follows or holds
        opp_team = 1 - team
        cands = [d for d in self.members[opp_team] if d != self.gk[opp_team] and d not in self.follow]
        follower = holder = None
        if cands:
            dists = np.linalg.norm(self.pos[cands] - self.pos[i], axis=1)
            j = int(np.argmin(dists))
            if dists[j] < 12.0:
                d = cands[j]
                p_follow = np.clip(self.tactics[opp_team].marking_follow * (0.8 + 0.4 * self.work_rate[d]), 0.05, 0.95)
                if self.rng.random() < p_follow:
                    follower = d
                    self.follow[d] = i
                else:
                    holder = d
        run_id = f"run_{len(self.run_log) + 1:04d}"
        self.run_log.append(RunTruth(id=run_id, player=self.ids[i], team=self.clubs[team].code, type=kind,
                                     intent=intent, t_start=self.t, t_end=self.t + dur, period=self.period,
                                     followed_by=self.ids[follower] if follower is not None else None,
                                     held_by=self.ids[holder] if holder is not None else None, linked_to=linked_to))
        self.runs[i] = Run(truth_index=len(self.run_log) - 1, target=self._tf(tgt, team), t_end=self.t + dur,
                           follower=follower)
        if intent == "decoy" and follower is not None:
            self._plan_exploit(i, team, follower, run_id)

    def _plan_exploit(self, runner: int, team: int, follower: int, decoy_id: str) -> None:
        """A teammate attacks the space the dragged defender has just left."""
        zone = self.pos[follower].copy()
        cands = [j for j in self.members[team]
                 if j not in (runner, self.owner, self.gk[team]) and j not in self.runs
                 and self.roles[j] in ("FB", "WM", "CM", "AM", "W", "ST")]
        if not cands:
            return
        dists = np.linalg.norm(self.pos[cands] - zone, axis=1)
        k = int(np.argmin(dists))
        if dists[k] > 25.0:
            return
        target = zone + self._attack_dir(team) * 3.0
        self.pending_exploits.append((self.t + self.rng.uniform(0.5, 1.2), cands[k], target, decoy_id))

    def _launch_exploits(self) -> None:
        due = [p for p in self.pending_exploits if p[0] <= self.t]
        self.pending_exploits = [p for p in self.pending_exploits if p[0] > self.t]
        for _, j, target, decoy_id in due:
            team = self.team[j]
            if self.state == "dead" or self.poss_team != team or j in self.runs or j == self.owner:
                continue
            kind = "overlap" if self.roles[j] in ("FB", "WM") else "in_behind"
            self._launch_run(j, team, kind, self._tf(target, team), 4.0, "target", linked_to=decoy_id)

    def _end_run(self, i: int) -> None:
        run = self.runs.pop(i)
        self.run_log[run.truth_index].t_end = self.t
        if run.follower is not None:
            self.follow.pop(run.follower, None)
        self.run_cooldown[i] = self.t + 6.0

    def _run_intent(self, i: int) -> str | None:
        run = self.runs.get(i)
        return self.run_log[run.truth_index].intent if run else None


    def _update_ball(self) -> None:
        if self.state == "owned":
            o = self.owner
            sp = np.linalg.norm(self.vel[o])
            facing = self.vel[o] / sp if sp > 0.5 else self._attack_dir(self.team[o])
            self.ball[:2] = np.clip(self.pos[o] + facing * 0.5, [0.1, 0.1], [LENGTH - 0.1, WIDTH - 0.1])
            self.ball[2] = 0.0
            self.ball_vel[:2] = self.vel[o]
            self.ball_vel[2] = 0.0
            return
        if self.state != "air":
            return
        prev = self.ball.copy()
        self.ball, self.ball_vel = _ball_physics(self.ball, self.ball_vel)
        if self.shot_ctx is not None:
            self._shot_progress(prev)
            return
        if not in_play(self.ball[0], self.ball[1]):
            self._ball_out()
            return
        self._try_control()

    def _try_control(self) -> None:
        if self.ball[2] > 1.8:
            return
        d = np.linalg.norm(self.pos - self.ball[:2], axis=1)
        order = np.argsort(d)
        speed = float(np.linalg.norm(self.ball_vel[:2]))
        for i in order[:3]:
            if d[i] > CONTROL_RADIUS:
                break
            if self.t < self.control_cd[i] or (i == self.kicker and self.t - self.kick_t < 0.5):
                continue
            self.control_cd[i] = self.t + 0.4
            high = self.ball[2] > 0.6
            if self.pass_ctx is not None and i == self.pass_ctx.receiver:
                p = 0.97 - 0.015 * max(0.0, speed - 9.0) - 0.3 * (0.6 - self.first_touch[i]) - (0.12 if high else 0.0)
            elif self.pass_ctx is not None and self.team[i] != self.team[self.pass_ctx.passer]:
                p = 0.4 + 0.25 * self.tackling[i] - 0.02 * max(0.0, speed - 10.0)
            else:
                p = 0.88 + 0.1 * self.first_touch[i] - 0.02 * max(0.0, speed - 6.0)
            if self.rng.random() < np.clip(p, 0.15, 0.99):
                self._gain(i, header_chance=high)
            else:
                self._deflect(i)
            return

    def _deflect(self, i: int) -> None:
        if self.pass_ctx is not None:
            self._emit_pass("incomplete", end=self.ball[:2], recipient=None)
            self.pass_ctx = None
        ang = math.radians(self.rng.uniform(20, 70) * self.rng.choice([-1, 1]))
        c, s = math.cos(ang), math.sin(ang)
        v = self.ball_vel[:2] * 0.4
        self.ball_vel[:2] = [c * v[0] - s * v[1], s * v[0] + c * v[1]]
        self.ball_vel[2] = abs(self.ball_vel[2]) * 0.3
        self.last_touch = i
        self.kicker = i
        self.kick_t = self.t

    def _gain(self, i: int, header_chance: bool = False, via: str | None = None) -> None:
        team = self.team[i]
        if self.pass_ctx is not None:
            pc = self.pass_ctx
            if self.team[pc.passer] == team:
                self._emit_pass("complete", end=self.ball[:2], recipient=i)
            else:
                self._emit_pass("incomplete", end=self.ball[:2], recipient=None)
                self._emit("interception", team=team, player=i, start=self.pos[i])
            self.pass_ctx = None
        elif via is None and team != self.poss_team:
            self._emit("ball_recovery", team=team, player=i, start=self.pos[i])
        self.state = "owned"
        self.owner = i
        self.last_touch = i
        self.poss_team = team
        self.ball_vel[:] = 0.0
        self.carry_start = (self.pos[i].copy(), self.t)
        self.carry_dir = self._attack_dir(team) * 0.0
        self.carry_speed = 0.2
        pressure = self._pressure_on(i)
        self.decision_t = self.t + 0.35 + 0.5 * (1.0 - self.first_touch[i]) * (1.0 - pressure)
        me = self._tf(self.pos[i], team)
        in_box = me[0] > LENGTH - BOX_DEPTH and abs(me[1] - HALF_Y) < BOX_HALF_WIDTH
        if header_chance and in_box and self.rng.random() < 0.55:
            self._shoot(i, pressure, header=True)

    def _ball_out(self) -> None:
        x, y = self.ball[0], self.ball[1]
        last_team = self.team[self.last_touch] if self.last_touch >= 0 else self.poss_team
        if self.pass_ctx is not None:
            self._emit_pass("out", end=np.array([np.clip(x, 0, LENGTH), np.clip(y, 0, WIDTH)]), recipient=None)
            self.pass_ctx = None
        if y < 0 or y > WIDTH:
            kind, team = "throw_in", 1 - last_team
            spot = np.array([np.clip(x, 1.0, LENGTH - 1.0), 0.0 if y < 0 else WIDTH])
        else:
            end_right = x > LENGTH
            defending = 0 if attack_sign(0, self.period) == (-1 if end_right else 1) else 1
            if last_team == defending:
                kind, team = "corner", 1 - defending
                spot = np.array([LENGTH - 0.5 if end_right else 0.5, 0.5 if y < HALF_Y else WIDTH - 0.5])
            else:
                kind, team = "goal_kick", defending
                spot = np.array([LENGTH - 5.5 if end_right else 5.5, HALF_Y])
        self._emit("out_of_play", team=last_team, player=self.last_touch if self.last_touch >= 0 else None,
                   end=np.array([np.clip(x, 0, LENGTH), np.clip(y, 0, WIDTH)]), outcome=kind)
        delay = {"throw_in": self.rng.uniform(10, 25), "goal_kick": self.rng.uniform(20, 35),
                 "corner": self.rng.uniform(25, 45)}[kind]
        self._set_restart(kind, team, spot, delay)

    def _ball_out_behind(self, goal_x: float) -> None:
        """Deflected or tipped over the goal line by a defender."""
        self.ball[0] = goal_x + (0.5 if goal_x > HALF_X else -0.5)
        self.ball[1] = HALF_Y + self.rng.uniform(-12.0, 12.0)
        self._ball_out()

    def _set_restart(self, kind: str, team: int, spot: np.ndarray, delay: float) -> None:
        if kind == "goal_kick":
            taker = self.gk[team]
        elif kind == "kick_off":
            st = [i for i in self.members[team] if self.roles[i] in ("ST", "AM")]
            taker = st[0] if st else int(self.members[team][-1])
        else:
            cand = [i for i in self.members[team] if i != self.gk[team]]
            taker = min(cand, key=lambda i: float(np.linalg.norm(self.pos[i] - spot)))
        self.restart = Restart(kind=kind, team=team, spot=spot.astype(float), at=self.t + delay, taker=taker)
        self.state = "dead"
        self.owner = -1
        self.pass_ctx = self.shot_ctx = None
        self.ball[:2] = spot
        self.ball[2] = 0.0
        self.ball_vel[:] = 0.0
        for i in list(self.runs):
            self._end_run(i)
        self.pending_exploits.clear()

    def _dead_logic(self) -> None:
        r = self.restart
        if r is None or self.t < r.at:
            return
        self.pos[r.taker] = r.spot
        self.vel[r.taker] = 0.0
        if r.kind == "kick_off":
            self._emit("kick_off", team=r.team, player=r.taker, start=r.spot)
        self.state = "owned"
        self.owner = r.taker
        self.poss_team = r.team
        self.last_touch = r.taker
        self.carry_start = None
        self.restart = None
        self._decide(r.taker, 0.0, set_piece=r.kind)


    def _shot_progress(self, prev: np.ndarray) -> None:
        """Play out a shot whose outcome was decided at release."""
        sc = self.shot_ctx
        assert sc is not None
        team = self.team[sc.shooter]
        sign = self._sign(team)
        goal_x = LENGTH if sign == 1 else 0.0
        crossed = (self.ball[0] >= goal_x) if sign == 1 else (self.ball[0] <= goal_x)

        if sc.outcome == "blocked" and sc.block_point is not None and not crossed:
            if _segment_distance(prev[:2], self.ball[:2], sc.block_point) < 1.0:
                self._emit_shot()
                self.shot_ctx = None
                self.last_touch = self.kicker = sc.blocker if sc.blocker is not None else sc.shooter
                self.kick_t = self.t
                if self.rng.random() < 0.35:
                    self._ball_out_behind(goal_x)
                    return
                ang = self.rng.uniform(0, 2 * math.pi)
                self.ball_vel[:] = [math.cos(ang) * 6.0, math.sin(ang) * 6.0, 1.5]
            return

        if sc.outcome == "saved":
            gk = self.gk[1 - team]
            if _segment_distance(prev[:2], self.ball[:2], self.pos[gk]) < 1.8 or crossed:
                self._emit_shot()
                self.shot_ctx = None
                self.ball[:2] = self.pos[gk] - self._attack_dir(1 - team) * -0.5
                self.ball[2] = 0.5
                roll = self.rng.random()
                if roll < 0.55:
                    self._gain(gk, via="save")
                elif roll < 0.75:
                    self.last_touch = gk
                    self._ball_out_behind(goal_x)
                else:
                    # parried back into play
                    self.last_touch = self.kicker = gk
                    self.kick_t = self.t
                    ang = self.rng.uniform(-1.0, 1.0)
                    self.ball_vel[:] = [-sign * 7.0 * math.cos(ang), 7.0 * math.sin(ang), 2.0]
            return

        if crossed:
            if sc.outcome == "blocked":
                sc.outcome = "off_target"
            self._emit_shot()
            self.shot_ctx = None
            if sc.outcome == "goal":
                self._emit("goal", team=team, player=sc.shooter, start=self.ball[:2])
                self._set_restart("kick_off", 1 - team, np.array([HALF_X, HALF_Y]), delay=self.rng.uniform(60, 90))
            else:
                self.last_touch = sc.shooter
                self._ball_out()
        elif not in_play(self.ball[0], self.ball[1]):
            self._emit_shot()
            self.shot_ctx = None
            self.last_touch = sc.shooter
            self._ball_out()

    def _shoot(self, i: int, pressure: float, header: bool = False, set_piece: str | None = None) -> None:
        team = self.team[i]
        sign = self._sign(team)
        me_tf = self._tf(self.pos[i], team)
        xg = xg_true(me_tf, pressure, header)
        start = self.ball[:2].copy() if not header else self.pos[i].copy()
        goal_x = LENGTH if sign == 1 else 0.0

        # blockers: defenders near the shot line in the first 8 m
        blocker, block_point = None, None
        aim_centre = np.array([goal_x, HALF_Y])
        line = aim_centre - start
        line_len = float(np.linalg.norm(line))
        unit = line / max(line_len, 1e-6)
        for d in self.members[1 - team]:
            if d == self.gk[1 - team]:
                continue
            rel = self.pos[d] - start
            along = float(np.dot(rel, unit))
            across = abs(float(rel[0] * unit[1] - rel[1] * unit[0]))
            if 0.8 < along < 11.0 and across < 1.4 and self.rng.random() < 0.65:
                blocker, block_point = d, start + unit * along
                break

        rng = self.rng
        p_goal = xg * (0.7 + 0.6 * self.finishing[i])
        p_on = np.clip(0.2 + 0.4 * self.finishing[i] - 0.2 * pressure, 0.12, 0.75)
        if blocker is not None:
            outcome = "blocked"
        elif rng.random() < p_goal:
            outcome = "goal"
        elif rng.random() < max(0.0, p_on - p_goal) / max(1e-6, 1.0 - p_goal):
            outcome = "saved"
        else:
            outcome = "off_target"

        gk = self.gk[1 - team]
        if outcome == "goal":
            ty, tz = HALF_Y + rng.choice([-1, 1]) * rng.uniform(0.6, GOAL_HALF_WIDTH - 0.3), rng.uniform(0.1, 2.2)
        elif outcome == "saved":
            ty, tz = np.clip(self.pos[gk, 1] + rng.normal(0, 1.2), HALF_Y - 3.3, HALF_Y + 3.3), rng.uniform(0.2, 1.8)
        else:
            if rng.random() < 0.6:
                ty, tz = HALF_Y + rng.choice([-1, 1]) * rng.uniform(4.0, 9.0), rng.uniform(0.2, 2.0)
            else:
                ty, tz = HALF_Y + rng.uniform(-3.0, 3.0), rng.uniform(2.6, 5.0)
        target = np.array([goal_x + 0.5 * sign, ty])
        v = (rng.uniform(14.0, 20.0) if header else 20.0 + 10.0 * rng.random() * (0.6 + 0.4 * self.finishing[i]))
        dist = float(np.linalg.norm(target - start))
        tflight = dist / v
        vz = (tz + 0.5 * G * tflight**2) / tflight
        direction = (target - start) / max(dist, 1e-6)
        self._end_carry(i)
        self.ball[:2] = start
        self.ball[2] = 1.6 if header else 0.1
        if header:
            vz = (tz - 1.6 + 0.5 * G * tflight**2) / tflight
        self.ball_vel[:] = [direction[0] * v, direction[1] * v, vz]
        self.state = "air"
        self.owner = -1
        self.kicker = i
        self.last_touch = i
        self.kick_t = self.t
        body = "head" if header else self._foot(i)
        self.shot_ctx = ShotInFlight(shooter=i, start=start, release_t=self.t, outcome=outcome, body_part=body,
                                     blocker=blocker, block_point=block_point, set_piece=set_piece)


    def _carrier_logic(self) -> None:
        i = self.owner
        pressure = self._pressure_on(i)
        urgent = pressure > 0.75 and self.t - self.last_decision_t > 0.4
        if self.t >= self.decision_t or urgent:
            self._decide(i, pressure)
        # keep the carrier inside the pitch
        if not (1.0 < self.pos[i, 0] < LENGTH - 1.0) or not (1.0 < self.pos[i, 1] < WIDTH - 1.0):
            self.carry_dir = (np.array([HALF_X, HALF_Y]) - self.pos[i])
            self.carry_dir /= max(np.linalg.norm(self.carry_dir), 1e-6)

    def _decide(self, i: int, pressure: float, set_piece: str | None = None) -> None:
        self.last_decision_t = self.t
        team = self.team[i]
        tac: Tactics = self.tactics[team]
        sign = self._sign(team)
        p = self.pos[i]
        me_tf = to_team_frame(p, sign)
        cur = threat(me_tf)

        options: list[tuple[float, str, object]] = []
        for j in self.members[team]:
            if j == i:
                continue
            dist = float(np.linalg.norm(self.pos[j] - p))
            max_d = 30.0 if set_piece == "throw_in" else 60.0
            if dist < 4.0 or dist > max_d:
                continue
            if set_piece not in ("throw_in", "corner", "goal_kick") and self._is_offside(j) \
                    and self.rng.random() > 0.12 * (1.0 - self.vision[i]):
                continue
            lead = np.clip(dist / 14.0, 0.3, 1.6)
            if self._run_intent(j) == "target":
                lead *= 1.3
            tgt = np.clip(self.pos[j] + self.vel[j] * lead, [1.0, 1.0], [LENGTH - 1.0, WIDTH - 1.0])
            tgt_d = float(np.linalg.norm(tgt - p))
            lofted = set_piece in ("corner", "throw_in") or tgt_d > 32.0
            p_ok = self._pass_success(i, tgt, lofted)
            tgt_tf = to_team_frame(tgt, sign)
            value = threat(tgt_tf) + 0.015
            progress = (tgt_tf[0] - me_tf[0]) / 60.0
            u = p_ok * value - (1.0 - p_ok) * self._loss_cost(tgt, team) + tac.directness * progress * 0.03
            if j == self.gk[team]:
                u -= 0.02 * (1.0 - pressure)
            if self._run_intent(j) == "decoy":
                u -= 0.08
            elif self._run_intent(j) == "target":
                u += 0.02
                if self.run_log[self.runs[j].truth_index].linked_to:
                    u += 0.05  # a teammate attacking space a decoy just opened is the obvious pass
            if set_piece == "corner" and not (tgt_tf[0] > LENGTH - BOX_DEPTH):
                u -= 0.05
            options.append((u, "pass", (j, tgt, lofted)))

        if set_piece is None:
            fwd = self._attack_dir(team)
            for deg in (-50, -20, 0, 20, 50):
                a = math.radians(deg)
                d = np.array([fwd[0] * math.cos(a) - fwd[1] * math.sin(a), fwd[0] * math.sin(a) + fwd[1] * math.cos(a)])
                ahead = p + d * 5.0
                if not (1.0 < ahead[0] < LENGTH - 1.0 and 1.0 < ahead[1] < WIDTH - 1.0):
                    continue
                opp = self.members[1 - team]
                space = float(np.min(np.linalg.norm(self.pos[opp] - ahead, axis=1)))
                p_keep = np.clip(0.2 + 0.1 * space + 0.2 * self.dribbling[i] - 0.35 * pressure, 0.05, 0.95)
                in_path = min(_segment_distance(p, ahead, self.pos[k]) for k in opp)
                if in_path < 1.5:
                    p_keep *= 0.4
                u = p_keep * (threat(to_team_frame(ahead, sign)) + 0.015) - (1 - p_keep) * self._loss_cost(p, team)
                options.append((u, "carry", d))
            risk = 0.1 + 0.3 * pressure
            options.append(((1 - risk) * cur - risk * self._loss_cost(p, team), "hold", None))

        if set_piece is None and me_tf[0] < 30.0 and pressure > 0.35:
            options.append((0.0, "clear", None))

        dist_goal = math.hypot(LENGTH - me_tf[0], HALF_Y - me_tf[1])
        if (set_piece in (None, "free_kick")) and dist_goal < 30.0 and me_tf[0] > 75.0:
            xg = xg_true(me_tf, pressure)
            if xg > SHOT_MIN_XG:
                options.append((SHOT_BIAS * xg - 0.01, "shoot", None))

        if not options:
            options.append((0.0, "hold", None))
        utils = np.array([o[0] for o in options])
        temp = 0.006 + 0.02 * (1.0 - self.vision[i]) + 0.008 * pressure
        w = np.exp((utils - utils.max()) / temp)
        choice = options[int(self.rng.choice(len(options), p=w / w.sum()))]
        kind = choice[1]
        if kind == "pass":
            j, tgt, lofted = choice[2]  # type: ignore[misc]
            self._kick_pass(i, j, tgt, lofted, pressure, set_piece)
        elif kind == "shoot":
            self._shoot(i, pressure, set_piece=set_piece)
        elif kind == "clear":
            self._clear(i)
        elif kind == "carry":
            self.carry_dir = choice[2]  # type: ignore[assignment]
            self.carry_speed = 0.55 + 0.2 * self.dribbling[i]
            self.decision_t = self.t + self.rng.uniform(0.5, 1.3) * (1.25 - 0.5 * tac.tempo)
        else:
            self.carry_dir = -self._attack_dir(team) * 0.3
            self.carry_speed = 0.2
            self.decision_t = self.t + self.rng.uniform(0.3, 0.8)

    def _clear(self, i: int) -> None:
        """Hoof the ball long and away from goal, with little control over where it lands."""
        team = self.team[i]
        ang = math.radians(self.rng.uniform(-40, 40))
        fwd = self._attack_dir(team)
        d = np.array([fwd[0] * math.cos(ang) - fwd[1] * math.sin(ang), fwd[0] * math.sin(ang) + fwd[1] * math.cos(ang)])
        dist = self.rng.uniform(30, 60)
        start = self.ball[:2].copy()
        vh = 14.0 + 0.2 * dist
        tflight = dist / vh
        self._end_carry(i)
        self.ball_vel[:] = [d[0] * vh, d[1] * vh, 0.5 * G * tflight]
        self.ball[2] = 0.3
        self.state = "air"
        self.owner = -1
        self.kicker = self.last_touch = i
        self.kick_t = self.t
        self._emit("clearance", team=team, player=i, start=start, end=start + d * dist, body_part=self._foot(i))

    def _loss_cost(self, at: np.ndarray, team: int) -> float:
        return 0.04 + 0.5 * threat(to_team_frame(at, -self._sign(team)))

    def _pass_success(self, i: int, tgt: np.ndarray, lofted: bool) -> float:
        p0 = self.pos[i]
        d = tgt - p0
        length = float(np.linalg.norm(d))
        if length < 1e-6:
            return 0.0
        s = np.linspace(0.15, 1.0, 10) * length
        pts = p0 + (d / length) * s[:, None]
        if lofted:
            vh = 13.0 + 0.17 * length
            t_ball = s / vh
            valid = s / length > 0.75
        else:
            v0 = min(28.0, math.sqrt(64.0 + 2 * ROLL_DECEL * length))
            disc = np.maximum(v0**2 - 2 * ROLL_DECEL * s, 0.0)
            t_ball = (v0 - np.sqrt(disc)) / ROLL_DECEL
            valid = np.ones_like(s, dtype=bool)
        opp = self.members[1 - self.team[i]]
        dist = np.linalg.norm(pts[None, :, :] - self.pos[opp][:, None, :], axis=2)
        t_reach = 0.3 + np.maximum(dist - 1.0, 0.0) / (self.top_speed[opp][:, None] * 0.9)
        margin = (t_reach - t_ball[None, :])[:, valid].min(axis=1)
        p_int = 1.0 / (1.0 + np.exp(margin * 5.0))
        p_clear = float(np.prod(1.0 - 0.8 * p_int))
        r = float(np.min(np.linalg.norm(self.pos[opp] - tgt, axis=1)))
        p_rec = 1.0 - 0.35 * math.exp(-r / 2.0)
        acc = 1.0 - min(0.5, (length / 55.0) ** 2 * (1.15 - self.passing[i]))
        if lofted:
            acc *= 0.85
        return p_clear * p_rec * acc

    def _kick_pass(self, i: int, j: int, tgt: np.ndarray, lofted: bool, pressure: float,
                   set_piece: str | None) -> None:
        start = self.ball[:2].copy()
        if set_piece not in ("throw_in", "corner", "goal_kick") and self._is_offside(j):
            self._end_carry(i)
            self._emit("pass", team=self.team[i], player=i, start=start, end=self.pos[j], recipient=j,
                       outcome="offside", height="high" if lofted else "ground", body_part=self._foot(i),
                       set_piece=set_piece)
            self._set_restart("free_kick", 1 - self.team[i], self.pos[j].copy(), delay=self.rng.uniform(10, 20))
            return
        length = float(np.linalg.norm(tgt - start))
        sigma = (0.25 + 0.035 * length) * (1.25 - self.passing[i]) + 0.5 * pressure
        if self.rng.random() < 0.06 * (1.2 - self.passing[i]) + 0.08 * pressure:
            sigma *= 6.0  # a misplaced pass
        aim = tgt + self.rng.normal(0, sigma, 2)
        d = aim - start
        dist = max(float(np.linalg.norm(d)), 0.5)
        unit = d / dist
        if lofted:
            vh = 13.0 + 0.17 * dist if set_piece != "throw_in" else 11.0
            tflight = dist / vh
            self.ball_vel[:] = [unit[0] * vh, unit[1] * vh, 0.5 * G * tflight]
            self.ball[2] = 0.3 if set_piece != "throw_in" else 1.8
        else:
            v_end = 7.0 + 2.0 * self.tactics[self.team[i]].tempo
            v0 = min(28.0, math.sqrt(v_end**2 + 2 * ROLL_DECEL * dist))
            self.ball_vel[:] = [unit[0] * v0, unit[1] * v0, 0.0]
            self.ball[2] = 0.0
        self._end_carry(i)
        self.state = "air"
        self.owner = -1
        self.kicker = i
        self.last_touch = i
        self.kick_t = self.t
        self.pass_ctx = PassInFlight(passer=i, receiver=j, start=start, release_t=self.t,
                                     height="high" if lofted else "ground", set_piece=set_piece,
                                     body_part="other" if set_piece == "throw_in" else self._foot(i))

    def _foot(self, i: int) -> str:
        preferred = "left_foot" if self.players[i].foot == "left" else "right_foot"
        other = "right_foot" if preferred == "left_foot" else "left_foot"
        return preferred if self.rng.random() < 0.8 else other

    def _end_carry(self, i: int) -> None:
        if self.carry_start is None:
            return
        start, t0 = self.carry_start
        self.carry_start = None
        if np.linalg.norm(self.pos[i] - start) >= 3.0:
            self._emit("carry", team=self.team[i], player=i, start=start, end=self.pos[i], t=t0,
                       duration=round(self.t - t0, 1))


    def _duels(self) -> None:
        c = self.owner
        opp = self.members[1 - self.team[c]]
        d = np.linalg.norm(self.pos[opp] - self.pos[c], axis=1)
        for idx in np.argsort(d):
            k = int(opp[idx])
            if d[idx] > TACKLE_RANGE:
                break
            near_goal = self._tf(self.pos[c], self.team[c])[0] > LENGTH - 25.0
            if self.t < self.tackle_cd[k] or self.rng.random() > (0.04 if near_goal else 0.02):
                continue
            self.tackle_cd[k] = self.t + 4.0
            if self.rng.random() < 0.06 + 0.06 * (1.0 - self.tackling[k]):
                self._emit("foul", team=self.team[k], player=k, opponent=c, start=self.pos[k])
                self._end_carry(c)
                self._set_restart("free_kick", self.team[c], self.ball[:2].copy(), delay=self.rng.uniform(20, 40))
                return
            p_win = np.clip(0.32 + 0.4 * (self.tackling[k] - self.dribbling[c]), 0.12, 0.7)
            if self.rng.random() < p_win:
                self._emit("tackle", team=self.team[k], player=k, opponent=c, start=self.pos[k], outcome="won")
                self._end_carry(c)
                if self.rng.random() < 0.65:
                    self._gain(k, via="tackle")
                else:
                    self.state = "air"
                    self.owner = -1
                    self.last_touch = self.kicker = k
                    self.kick_t = self.t
                    ang = self.rng.uniform(0, 2 * math.pi)
                    sp = self.rng.uniform(4.0, 7.0)
                    self.ball_vel[:] = [math.cos(ang) * sp, math.sin(ang) * sp, 0.0]
            else:
                self._emit("tackle", team=self.team[k], player=k, opponent=c, start=self.pos[k], outcome="lost")
            return

    def _pressure_events(self) -> None:
        c = self.owner
        opp = self.members[1 - self.team[c]]
        rel = self.pos[c] - self.pos[opp]
        r = np.linalg.norm(rel, axis=1)
        closing = np.einsum("ij,ij->i", self.vel[opp] - self.vel[c], rel / np.maximum(r, 1e-6)[:, None])
        if self.engaged_carrier != c:
            self.engaged_carrier = c
            self.engaged.clear()
        for idx in range(len(opp)):
            k = int(opp[idx])
            if r[idx] > 5.0:
                self.engaged.discard(k)
            elif k not in self.engaged and r[idx] < 3.5 and closing[idx] > 1.0:
                self.engaged.add(k)
                self._emit("pressure", team=self.team[k], player=k, opponent=c, start=self.pos[k])


    def _emit(self, etype: str, *, team: int | None = None, player: int | None = None,
              start: np.ndarray | None = None, end: np.ndarray | None = None, recipient: int | None = None,
              opponent: int | None = None, outcome: str | None = None, height: str | None = None,
              body_part: str | None = None, set_piece: str | None = None, duration: float | None = None,
              t: float | None = None) -> None:
        self.event_n += 1
        e: dict = {"id": f"ev_{self.event_n}", "match": self.match_id, "t": round(t if t is not None else self.t, 1),
                   "period": self.period, "source": "sim", "type": etype}
        if team is not None:
            e["team"] = self.clubs[int(team)].code
        if player is not None:
            e["player"] = self.ids[int(player)]
        if start is not None:
            e["start"] = [round(float(start[0]), 2), round(float(start[1]), 2)]
        if end is not None:
            e["end"] = [round(float(end[0]), 2), round(float(end[1]), 2)]
        if recipient is not None:
            e["recipient"] = self.ids[int(recipient)]
        if opponent is not None:
            e["opponent"] = self.ids[int(opponent)]
        for key, val in (("outcome", outcome), ("height", height), ("body_part", body_part),
                         ("set_piece", set_piece), ("duration", duration)):
            if val is not None:
                e[key] = val
        self.events.append(e)
        self._on_event(e)

    def _emit_pass(self, outcome: str, end: np.ndarray, recipient: int | None) -> None:
        pc = self.pass_ctx
        assert pc is not None
        self._emit("pass", team=self.team[pc.passer], player=pc.passer, start=pc.start, end=end,
                   recipient=recipient, outcome=outcome, height=pc.height, body_part=pc.body_part,
                   set_piece=pc.set_piece, t=pc.release_t)

    def _emit_shot(self) -> None:
        sc = self.shot_ctx
        assert sc is not None
        self._emit("shot", team=self.team[sc.shooter], player=sc.shooter, start=sc.start, end=self.ball[:2],
                   outcome=sc.outcome, body_part=sc.body_part, set_piece=sc.set_piece, t=sc.release_t)

    def _frame(self) -> dict:
        return {
            "match": self.match_id,
            "t": self.t,
            "period": self.period,
            "source": "sim",
            "ball": [round(float(self.ball[0]), 2), round(float(self.ball[1]), 2), round(float(self.ball[2]), 2)],
            "players": {pid: [round(float(self.pos[i, 0]), 2), round(float(self.pos[i, 1]), 2)]
                        for i, pid in enumerate(self.ids)},
        }


def _segment_distance(a: np.ndarray, b: np.ndarray, p: np.ndarray) -> float:
    """Distance from point p to the segment a-b (the ball's path during one tick)."""
    ab = b - a
    denom = float(np.dot(ab, ab))
    s = 0.0 if denom < 1e-12 else float(np.clip(np.dot(p - a, ab) / denom, 0.0, 1.0))
    return float(np.linalg.norm(a + s * ab - p))


def _ball_physics(p: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """One tick of ball motion: flight with gravity and bounces, then rolling friction."""
    p = p.copy()
    v = v.copy()
    if p[2] > 0.01 or v[2] > 0.01:
        v[2] -= G * DT
        p += v * DT
        if p[2] <= 0.0:
            p[2] = 0.0
            if v[2] < -1.5:
                v[2] = -0.45 * v[2]
                v[:2] *= 0.75
            else:
                v[2] = 0.0
    else:
        sp = math.hypot(v[0], v[1])
        if sp > 0.0:
            new = max(0.0, sp - ROLL_DECEL * DT)
            v[:2] *= new / sp
        p[:2] += v[:2] * DT
        p[2] = 0.0
    return p, v

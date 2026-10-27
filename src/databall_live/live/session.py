"""A live broadcast: one shared match clock, the insight crew running as play unfolds, and a producer in control.

The crew runs beside the clock, never in its way: when the model is slow the match keeps playing, and a crew that
falls too far behind catches up from the cache and templates instead of airing stale graphics.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import OrderedDict
from dataclasses import dataclass, field

from fastapi import WebSocket

from ..insights.cache import Cache
from ..insights.crew import MomentBatch, Timings, build_crew, minute_batches, run_batch
from ..insights.foundry import Foundry, settings
from ..stats.analyse import Analysis, analyse
from ..stats.season import Season
from .predictions import Prediction, Predictor
from .store import Bundle, MatchStore, frame_message, state_message
from .viewer import Viewer

LIVE_STEP_S = 10.0
APPROVAL_WINDOW_S = 20.0
LOWER_THIRD_S = 12.0
CATCH_UP_S = 45.0
TRANSPORT = {"play", "pause", "speed", "seek"}
CATCH_UP_GROUP = 18
INGEST_SKIP = {"carry", "out_of_play", "half_start", "half_end"}
GAINS = {"pass", "shot", "tackle", "interception", "ball_recovery"}
MAX_SESSIONS = 6
MAX_ANALYSES = 4


@dataclass
class Control:
    mode: str = "auto"
    killed: bool = False
    disabled: set[str] = field(default_factory=set)
    unreliable: float = 0.0
    model: bool = False

    def as_dict(self) -> dict:
        return {"mode": self.mode, "killed": self.killed, "disabled": sorted(self.disabled),
                "unreliable": self.unreliable, "model": self.model}


def _before(a: tuple[int, float], b: tuple[int, float]) -> bool:
    return a[0] < b[0] or (a[0] == b[0] and a[1] <= b[1])


class LiveSession:
    def __init__(self, bundle: Bundle, analysis: Analysis, foundry: Foundry | None = None,
                 cache: Cache | None = None, season: Season | None = None) -> None:
        self.b = bundle
        self.a = analysis
        self.foundry = foundry
        self.cache = cache or Cache()
        self.season = season or Season([])
        self.detections = sorted(analysis.patterns, key=lambda p: (p.period, p.t_end))
        self.detect_k = 0
        self.ingest = sorted((e for e in bundle.md.events if e["type"] not in INGEST_SKIP),
                             key=lambda e: (e["period"], e["t"]))
        self.ingest_k = 0
        self.possession: str | None = None
        self.pass_by_event = {p["event"]: p for p in bundle.metrics["passes"]}
        self.shot_by_event = {x["event"]: x for x in bundle.metrics["shots"]}
        self.control = Control(model=foundry is not None)
        self.speed = 1.0
        self.playing = False
        self.k = 0
        self.viewers: dict[WebSocket, Viewer] = {}
        self.consoles: set[WebSocket] = set()
        self.approvals: dict[str, str] = {}
        self.statuses: dict[str, str] = {}
        self.insights: dict[str, dict] = {}
        self.held: list[tuple[dict, float]] = []
        self.aired: list[dict] = []
        self.notes: list[dict] = []
        self.task: asyncio.Task | None = None
        self.crew_task: asyncio.Task | None = None
        self._reset_crew()

    def _reset_crew(self) -> None:
        self.crew = build_crew(self.a, unreliable=self.control.unreliable, foundry=self.foundry, cache=self.cache,
                               live=True, season=self.season)
        self.crew.switch.mode = "live" if self.control.model else "off"
        ends = {p: end for p, (_, end) in self.b.period_bounds.items()}
        self.predictor = Predictor(self.a.md, self.crew.names.team, ends)
        self.calls: list[tuple[tuple[int, float], dict]] = []
        self.timings = Timings()
        self.batches = minute_batches(self.a, LIVE_STEP_S)
        self.next_batch = 0
        self.queue: list[dict] = []
        self.pointer = 0
        self.focus: set[str] = set()
        self.seen_drafts = 0
        self.rejections = 0
        self.fallbacks = 0

    @property
    def now(self) -> tuple[int, float]:
        md = self.b.md
        return int(md.period[self.k]), float(md.t[self.k])

    async def _send(self, sockets: list[WebSocket], message: dict) -> None:
        results = await asyncio.gather(*(ws.send_json(message) for ws in sockets), return_exceptions=True)
        for ws, result in zip(sockets, results, strict=True):
            if isinstance(result, Exception):
                self.viewers.pop(ws, None)
                self.consoles.discard(ws)

    async def to_consoles(self, message: dict) -> None:
        await self._send(list(self.consoles), message)

    async def to_viewers(self, message: dict) -> None:
        await self._send(list(self.viewers), message)

    def snapshot(self) -> dict:
        period, t = self.now
        return {"kind": "hello", "match": self.b.id, "playing": self.playing, "speed": self.speed, "period": period,
                "t": t, "control": self.control.as_dict(), "crew": self.crew_report(),
                "insights": [{**v, "status": self.statuses.get(k, "queued")} for k, v in self.insights.items()],
                "notes": self.notes}

    def crew_report(self) -> dict:
        return {"executors": self.timings.report(), "insights": len(self.insights), "rejections": self.rejections,
                "fallbacks": self.fallbacks, "unreliable": self.control.unreliable,
                "model": self.foundry.report() if self.foundry else None}

    def _model_mode(self, batch_t: tuple[int, float], silent: bool) -> str:
        if not self.control.model:
            return "off"
        period, t = self.now
        behind = period > batch_t[0] or t - batch_t[1] > CATCH_UP_S
        return "cache" if silent or behind else "live"

    async def _run_crew(self, until: tuple[int, float], silent: bool = False) -> None:
        while self.next_batch < len(self.batches):
            batch = self.batches[self.next_batch]
            if not _before((batch.period, batch.t), until):
                break
            group = [batch]
            while silent and len(group) < CATCH_UP_GROUP and not group[-1].close_period:
                k = self.next_batch + len(group)
                if k >= len(self.batches) or self.batches[k].period != batch.period:
                    break
                if not _before((self.batches[k].period, self.batches[k].t), until):
                    break
                group.append(self.batches[k])
            self.next_batch += len(group)
            if len(group) > 1:
                batch = MomentBatch(group[-1].period, group[-1].t, [p for g in group for p in g.patterns],
                                    [x for g in group for x in g.state], group[-1].close_period)
            self.crew.switch.mode = self._model_mode((batch.period, batch.t), silent)
            packets, notes = await run_batch(self.crew, batch, self.timings)
            self.cache.save()
            for note in notes:
                if note.kind == "rejected":
                    self.rejections += 1
                elif note.kind == "fallback":
                    self.fallbacks += note.detail["count"]
                if not silent:
                    message = {"kind": "note", "executor": note.executor, "note": note.kind, "detail": note.detail}
                    self.notes = [message, *self.notes][:30]
                    await self.to_consoles(message)
            await self._new_insights(silent)
            period, t = until
            fresh = []
            for p in packets:
                d = p.model_dump(exclude_none=True)
                if d["persona"] == "player_focus" and d.get("insight"):
                    self.focus.add(d["insight"])
                if silent and _before((d["period"], d["show_at"]), until):
                    if d["slot"] == "lower_third":
                        self.aired.append(d)
                        self.statuses[d["insight"]] = "aired"
                    continue
                if d["period"] == period and d["show_at"] < t:
                    length = d["expires_at"] - d["show_at"]
                    d["show_at"] = round(t + 0.5, 1)
                    d["expires_at"] = round(t + 0.5 + length, 1)
                fresh.append(d)
            self.queue = self.queue[:self.pointer] + sorted(
                self.queue[self.pointer:] + fresh, key=lambda d: (d["period"], d["show_at"], d["priority"]))
            if not silent:
                await self.to_consoles({"kind": "crew", **self.crew_report()})

    async def _new_insights(self, silent: bool) -> None:
        history = self.crew.editor.history
        variants = self.crew.producer.approved
        for d in history[self.seen_drafts:]:
            ins = d.insight
            lines: dict[str, dict[str, dict]] = {}
            for v in variants:
                if v.insight == ins.id:
                    lines.setdefault(v.lang, {})[v.persona] = {"headline": v.headline, "body": v.body,
                                                               "source": v.source}
            payload = {"id": ins.id, "type": ins.type, "period": ins.period, "t": ins.t, "claim": ins.claim,
                       "mechanism": ins.mechanism, "consequence": ins.consequence, "signals": ins.signals,
                       "confidence": ins.confidence, "significance": ins.significance, "entities": ins.entities,
                       "model": ins.model.model_dump(), "tools": d.tools, "why": d.why, "lines": lines}
            self.insights[ins.id] = payload
            if not silent:
                await self.to_consoles({"kind": "insight", **payload, "status": self.statuses.get(ins.id, "queued")})
        self.seen_drafts = len(history)

    async def _status(self, insight: str | None, status: str) -> None:
        if insight is None or self.statuses.get(insight) == status:
            return
        self.statuses[insight] = status
        period, t = self.now
        await self.to_consoles({"kind": "status", "insight": insight, "status": status, "period": period, "t": t})

    async def _air(self, packet: dict) -> None:
        sends = [ws for ws, viewer in self.viewers.items() if viewer.wants(packet, packet.get("insight") in self.focus)]
        await self._send(sends, {"kind": "packet", **packet})
        if packet["slot"] == "lower_third":
            self.aired.append(packet)
            await self._status(packet.get("insight"), "aired")
            if packet["persona"] == "fan" and packet["lang"] == "en":
                data = packet.get("data", {})
                team = (data.get("teams") or [""])[0]
                period, t = self.now
                self._schedule(self.predictor.after_insight(data.get("type", ""), team, period, t))

    def _schedule(self, prediction: Prediction | None) -> None:
        if prediction is None:
            return
        self.calls.append(((prediction.period, prediction.opens), prediction.prompt))
        self.calls.append(((prediction.period, prediction.settled), prediction.result))
        self.calls.sort(key=lambda c: c[0])

    @staticmethod
    def _detection(p) -> dict:
        return {"id": p.id, "type": p.type, "actor": p.actor, "team": p.team, "period": p.period,
                "t": round(p.t_end, 1)}

    def recent_detections(self, n: int = 6) -> list[dict]:
        return [self._detection(p) for p in self.detections[max(0, self.detect_k - n):self.detect_k]]

    def _event(self, e: dict) -> dict:
        item = {"id": e["id"], "type": e["type"], "team": e.get("team"), "player": e.get("player"),
                "recipient": e.get("recipient"), "period": e["period"], "t": round(e["t"], 1),
                "outcome": e.get("outcome")}
        if e["type"] == "pass" and e["id"] in self.pass_by_event:
            m = self.pass_by_event[e["id"]]
            item.update(distance=round(m["distance_m"]), difficulty=round(m["difficulty"], 1),
                        speed=round(m["speed_kmh"]), complete=m["complete"])
        elif e["type"] == "shot" and e["id"] in self.shot_by_event:
            m = self.shot_by_event[e["id"]]
            item.update(speed=round(m["speed_kmh"]), xg=round(m["xg"] or 0.0, 2))
        return item

    def recent_events(self, n: int = 8) -> list[dict]:
        out = []
        team = None
        for e in self.ingest[:self.ingest_k]:
            if e["type"] in GAINS and e.get("team") and e["team"] != team:
                if team is not None:
                    out.append({"id": f"pos_{e['id']}", "type": "possession", "team": e["team"], "player": None,
                                "period": e["period"], "t": round(e["t"], 1)})
                team = e["team"]
            out.append(self._event(e))
        self.possession = team
        return out[-n:]

    async def _ingest(self) -> None:
        """Stream the incoming match events as the clock passes them, with possession changes."""
        fresh = []
        while self.ingest_k < len(self.ingest):
            e = self.ingest[self.ingest_k]
            if not _before((e["period"], e["t"]), self.now):
                break
            if e["type"] in GAINS and e.get("team") and e["team"] != self.possession:
                if self.possession is not None:
                    fresh.append({"id": f"pos_{e['id']}", "type": "possession", "team": e["team"], "player": None,
                                  "period": e["period"], "t": round(e["t"], 1)})
                self.possession = e["team"]
            fresh.append(self._event(e))
            self.ingest_k += 1
        if fresh:
            await self.to_viewers({"kind": "events", "items": fresh[-8:], "count": self.ingest_k})

    async def _detect(self) -> None:
        """Stream what the detectors see as the match clock passes it."""
        fresh = []
        while self.detect_k < len(self.detections):
            p = self.detections[self.detect_k]
            if not _before((p.period, p.t_end), self.now):
                break
            fresh.append(self._detection(p))
            self.detect_k += 1
        if fresh:
            await self.to_viewers({"kind": "detect", "items": fresh[-6:], "count": self.detect_k})

    async def _predictions(self) -> None:
        period, t = self.now
        start = self.b.period_bounds[period][0]
        self._schedule(self.predictor.periodic(period, t, start))
        while self.calls and _before(self.calls[0][0], (period, t)):
            _, message = self.calls.pop(0)
            if not self.control.killed:
                await self.to_viewers(message)

    async def send_history(self, ws: WebSocket, viewer: Viewer, limit: int = 80) -> None:
        """Graphics that already aired and suit this viewer, so joining or switching view never starts empty."""
        fitting = [p for p in self.aired if viewer.fits(p, p.get("insight") in self.focus)]
        await self._send([ws], {"kind": "history", "packets": fitting[-limit:]})

    async def _release(self) -> None:
        period, t = self.now
        while self.pointer < len(self.queue) and _before((self.queue[self.pointer]["period"],
                                                          self.queue[self.pointer]["show_at"]), (period, t)):
            packet = self.queue[self.pointer]
            self.pointer += 1
            insight = packet.get("insight")
            kind = packet.get("data", {}).get("type", "")
            if self.control.killed:
                await self._status(insight, "killed")
                continue
            if kind in self.control.disabled:
                await self._status(insight, "switched_off")
                continue
            if packet["slot"] == "lower_third" and self.control.mode == "supervised":
                decision = self.approvals.get(insight or "")
                if decision == "rejected":
                    await self._status(insight, "rejected")
                    continue
                if decision != "approved":
                    self.held.append((packet, t))
                    await self._status(insight, "awaiting_approval")
                    continue
            await self._air(packet)
        still = []
        for packet, due in self.held:
            decision = self.approvals.get(packet.get("insight") or "")
            if decision == "approved" and packet["period"] == period:
                await self._air({**packet, "show_at": round(t, 1), "expires_at": round(t + LOWER_THIRD_S, 1)})
            elif decision == "rejected":
                await self._status(packet.get("insight"), "rejected")
            elif t - due > min(APPROVAL_WINDOW_S * max(1.0, self.speed), 90.0) or packet["period"] != period:
                await self._status(packet.get("insight"), "expired")
            else:
                still.append((packet, due))
        self.held = still

    async def crew_loop(self) -> None:
        while True:
            if self.playing:
                await self._run_crew(self.now)
            await asyncio.sleep(0.2)

    async def run(self) -> None:
        md = self.b.md
        self.crew_task = asyncio.create_task(self.crew_loop())
        while True:
            if not self.playing or self.k >= len(md.t) - 1:
                if self.playing:
                    self.playing = False
                    await self.to_viewers({"kind": "end"})
                    await self._transport()
                await asyncio.sleep(0.1)
                continue
            frame = frame_message(self.b, self.k)
            await self.to_viewers(frame)
            if self.k % 2 == 0:
                await self.to_consoles(frame)
            await self._release()
            await self._predictions()
            await self._ingest()
            await self._detect()
            if self.k % (5 * md.hz) == 0:
                period, t = self.now
                await self._send(list(self.viewers) + list(self.consoles), state_message(self.b, period, t))
            step = max(1, int(round(self.speed)))
            await asyncio.sleep(0.1 * step / self.speed)
            self.k = min(self.k + step, len(md.t) - 1)

    async def _transport(self) -> None:
        message = {"kind": "transport", "playing": self.playing, "speed": self.speed}
        await self._send(list(self.viewers) + list(self.consoles), message)

    async def command(self, msg: dict) -> None:
        action = msg.get("action")
        if action == "play":
            self.playing = True
        elif action == "pause":
            self.playing = False
        elif action == "speed":
            self.speed = max(0.25, min(float(msg["value"]), 20.0))
        elif action == "seek":
            await self.seek(int(msg["period"]), float(msg["t"]))
        elif action == "mode":
            self.control.mode = "supervised" if msg["value"] == "supervised" else "auto"
        elif action == "kill":
            self.control.killed = bool(msg["value"])
            if self.control.killed:
                await self.to_viewers({"kind": "clear"})
        elif action == "type":
            (self.control.disabled.discard if msg["on"] else self.control.disabled.add)(msg["value"])
        elif action in ("approve", "reject"):
            self.approvals[msg["insight"]] = "approved" if action == "approve" else "rejected"
        elif action == "unreliable":
            self.control.unreliable = max(0.0, min(float(msg["value"]), 1.0))
            self.crew.storyteller.unreliable = self.control.unreliable
        elif action == "model":
            self.control.model = bool(msg["value"]) and self.foundry is not None
            self.crew.switch.mode = "live" if self.control.model else "off"
        if action in TRANSPORT:
            await self._transport()
        await self.to_consoles({"kind": "control", "playing": self.playing, "speed": self.speed,
                                "control": self.control.as_dict(), "approvals": self.approvals})

    async def seek(self, period: int, t: float) -> None:
        running = self.crew_task is not None
        if running:
            self.crew_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.crew_task
        self.k = self.b.frame(period, t)
        self._reset_crew()
        self.held = []
        self.aired = []
        self.insights = {}
        self.statuses = {}
        self.notes = []
        await self._run_crew(self.now, silent=True)
        if running:
            self.crew_task = asyncio.create_task(self.crew_loop())
        await self.to_viewers({"kind": "clear"})
        self.detect_k = sum(1 for p in self.detections if _before((p.period, p.t_end), self.now))
        await self.to_viewers({"kind": "detect", "items": self.recent_detections(), "count": self.detect_k})
        self.ingest_k = sum(1 for e in self.ingest if _before((e["period"], e["t"]), self.now))
        await self.to_viewers({"kind": "events", "items": self.recent_events(), "count": self.ingest_k})
        period, t = self.now
        await self._send(list(self.viewers) + list(self.consoles), frame_message(self.b, self.k))
        await self._send(list(self.viewers) + list(self.consoles), state_message(self.b, period, t))
        for ws, v in list(self.viewers.items()):
            v.reset()
            await self.send_history(ws, v)
        await self.to_consoles(self.snapshot())


class Sessions:
    """One live session per match and room, so each audience gets its own broadcast."""

    def __init__(self, store: MatchStore) -> None:
        self.store = store
        self.live: OrderedDict[str, LiveSession] = OrderedDict()
        self.analyses: OrderedDict[str, Analysis] = OrderedDict()
        self.caches: dict[str, Cache] = {}
        self.foundry: Foundry | None = None
        self.lock = asyncio.Lock()

    def model(self) -> Foundry | None:
        if self.foundry is None:
            found = settings()
            self.foundry = Foundry(found) if found else None
        return self.foundry

    async def _analysis(self, bundle: Bundle) -> Analysis:
        if bundle.id not in self.analyses:
            self.analyses[bundle.id] = await asyncio.to_thread(analyse, bundle.folder)
            while len(self.analyses) > MAX_ANALYSES:
                self.analyses.popitem(last=False)
        self.analyses.move_to_end(bundle.id)
        return self.analyses[bundle.id]

    def _evict(self) -> None:
        idle = [k for k, s in self.live.items() if not s.viewers and not s.consoles]
        while len(self.live) >= MAX_SESSIONS and idle:
            session = self.live.pop(idle.pop(0))
            for task in (session.task, session.crew_task):
                if task:
                    task.cancel()

    async def get(self, match_id: str, room: str = "main") -> LiveSession:
        key = f"{match_id}:{room}"
        async with self.lock:
            if key not in self.live:
                self._evict()
                bundle = self.store.get(match_id)
                cache = self.caches.setdefault(match_id, Cache(bundle.folder / "cache.json"))
                season = await asyncio.to_thread(Season.load, bundle.folder)
                session = LiveSession(bundle, await self._analysis(bundle), self.model(), cache, season)
                session.task = asyncio.create_task(session.run())
                self.live[key] = session
            self.live.move_to_end(key)
            return self.live[key]

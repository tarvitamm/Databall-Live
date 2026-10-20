"""A live broadcast: one shared match clock, the insight crew running as play unfolds, and a producer in control."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fastapi import WebSocket

from ..insights.crew import Timings, build_crew, minute_batches, run_batch
from ..stats.analyse import Analysis, analyse
from .store import Bundle, MatchStore, frame_message, state_message
from .viewer import Viewer

LIVE_STEP_S = 10.0
APPROVAL_WINDOW_S = 20.0
LOWER_THIRD_S = 12.0


@dataclass
class Control:
    mode: str = "auto"
    killed: bool = False
    disabled: set[str] = field(default_factory=set)
    unreliable: float = 0.0

    def as_dict(self) -> dict:
        return {"mode": self.mode, "killed": self.killed, "disabled": sorted(self.disabled),
                "unreliable": self.unreliable}


def _before(a: tuple[int, float], b: tuple[int, float]) -> bool:
    return a[0] < b[0] or (a[0] == b[0] and a[1] <= b[1])


class LiveSession:
    def __init__(self, bundle: Bundle, analysis: Analysis) -> None:
        self.b = bundle
        self.a = analysis
        self.control = Control()
        self.speed = 1.0
        self.playing = False
        self.k = 0
        self.viewers: dict[WebSocket, Viewer] = {}
        self.consoles: set[WebSocket] = set()
        self.approvals: dict[str, str] = {}
        self.statuses: dict[str, str] = {}
        self.insights: dict[str, dict] = {}
        self.held: list[tuple[dict, float]] = []
        self.notes: list[dict] = []
        self.task: asyncio.Task | None = None
        self._reset_crew()

    def _reset_crew(self) -> None:
        self.crew = build_crew(self.a, unreliable=self.control.unreliable)
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
                "fallbacks": self.fallbacks, "unreliable": self.control.unreliable}

    async def _run_crew(self, until: tuple[int, float], silent: bool = False) -> None:
        while self.next_batch < len(self.batches):
            batch = self.batches[self.next_batch]
            if not _before((batch.period, batch.t), until):
                break
            self.next_batch += 1
            packets, notes = await run_batch(self.crew, batch, self.timings)
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
            if silent:
                continue
            period, t = until
            fresh = []
            for p in packets:
                d = p.model_dump(exclude_none=True)
                if d["period"] == period and d["show_at"] < t:
                    length = d["expires_at"] - d["show_at"]
                    d["show_at"] = round(t + 0.5, 1)
                    d["expires_at"] = round(t + 0.5 + length, 1)
                if d["persona"] == "player_focus" and d.get("insight"):
                    self.focus.add(d["insight"])
                fresh.append(d)
            self.queue = self.queue[:self.pointer] + sorted(
                self.queue[self.pointer:] + fresh, key=lambda d: (d["period"], d["show_at"], d["priority"]))
            await self.to_consoles({"kind": "crew", **self.crew_report()})

    async def _new_insights(self, silent: bool) -> None:
        history = self.crew.editor.history
        variants = self.crew.producer.approved
        for d in history[self.seen_drafts:]:
            ins = d.insight
            lines: dict[str, dict[str, dict]] = {}
            for v in variants:
                if v.insight == ins.id:
                    lines.setdefault(v.lang, {})[v.persona] = {"headline": v.headline, "body": v.body}
            payload = {"id": ins.id, "type": ins.type, "period": ins.period, "t": ins.t, "claim": ins.claim,
                       "mechanism": ins.mechanism, "consequence": ins.consequence, "signals": ins.signals,
                       "confidence": ins.confidence, "significance": ins.significance, "entities": ins.entities,
                       "model": ins.model.model_dump(), "lines": lines}
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
            await self._status(packet.get("insight"), "aired")

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

    async def run(self) -> None:
        md = self.b.md
        while True:
            if not self.playing or self.k >= len(md.t) - 1:
                if self.playing:
                    self.playing = False
                    await self.to_viewers({"kind": "end"})
                    await self.to_consoles({"kind": "playing", "playing": False})
                await asyncio.sleep(0.1)
                continue
            await self._run_crew(self.now)
            frame = frame_message(self.b, self.k)
            await self.to_viewers(frame)
            if self.k % 2 == 0:
                await self.to_consoles(frame)
            await self._release()
            if self.k % (5 * md.hz) == 0:
                period, t = self.now
                await self._send(list(self.viewers) + list(self.consoles), state_message(self.b, period, t))
            step = max(1, int(round(self.speed)))
            await asyncio.sleep(0.1 * step / self.speed)
            self.k = min(self.k + step, len(md.t) - 1)

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
        await self.to_consoles({"kind": "control", "playing": self.playing, "speed": self.speed,
                                "control": self.control.as_dict(), "approvals": self.approvals})

    async def seek(self, period: int, t: float) -> None:
        self.k = self.b.frame(period, t)
        self._reset_crew()
        self.crew.storyteller.unreliable = self.control.unreliable
        self.held = []
        self.insights = {}
        self.statuses = {}
        self.notes = []
        await self._run_crew(self.now, silent=True)
        for v in self.viewers.values():
            v.reset()
        await self.to_viewers({"kind": "clear"})
        await self.to_consoles(self.snapshot())


class Sessions:
    def __init__(self, store: MatchStore) -> None:
        self.store = store
        self.live: dict[str, LiveSession] = {}
        self.lock = asyncio.Lock()

    async def get(self, match_id: str) -> LiveSession:
        async with self.lock:
            if match_id not in self.live:
                bundle = self.store.get(match_id)
                analysis = await asyncio.to_thread(analyse, bundle.folder)
                session = LiveSession(bundle, analysis)
                session.task = asyncio.create_task(session.run())
                self.live[match_id] = session
            return self.live[match_id]

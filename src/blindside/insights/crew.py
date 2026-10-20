"""The insight crew as a Microsoft Agent Framework workflow.

The router fans each minute of detected patterns out to the tactical analyst and the player lens, the editor joins
their drafts, the storyteller writes every persona and language, the verifier checks each line and sends failures
back for a rewrite, and the producer schedules what airs.
"""

from __future__ import annotations

import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Never

from agent_framework import (
    Executor,
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)

from ..contracts import OverlayPacket, Pattern
from ..stats.analyse import Analysis
from ..stats.state import StateBin
from .analyst import PLAYER, TACTICAL, Builder, Draft, RepeatGuard, draft_player, draft_state, draft_tactical
from .producer import TAG_SLOT, Scheduler
from .storyteller import Names, Variant, describe, render_all
from .text import LANGS
from .verifier import verify

MAX_ATTEMPTS = 3


@dataclass
class MomentBatch:
    period: int
    t: float
    patterns: list[Pattern]
    state: list[StateBin]
    close_period: bool = False


@dataclass
class AnalystTask:
    patterns: list[Pattern]
    state: list[StateBin]


@dataclass
class LensTask:
    patterns: list[Pattern]


@dataclass
class TagTask:
    patterns: list[Pattern]
    recap: tuple[int, float] | None


@dataclass
class Drafts:
    source: str
    drafts: list[Draft]


@dataclass
class Edited:
    drafts: list[Draft]


@dataclass
class Lines:
    drafts: list[Draft]
    variants: list[Variant]
    attempt: int
    fallback: set[tuple[str, str, str]] = field(default_factory=set)


@dataclass
class Rewrite:
    drafts: list[Draft]
    passed: list[Variant]
    failed: list[tuple[Variant, list[str]]]
    attempt: int


@dataclass
class Approved:
    drafts: list[Draft]
    variants: list[Variant]
    fallback: set[tuple[str, str, str]]


@dataclass
class CrewNote:
    executor: str
    kind: str
    detail: dict


@dataclass
class PacketBatch:
    packets: list[OverlayPacket]


def _template(d: Draft, v: Variant, names: Names) -> Variant:
    return next(x for x in render_all(d, names, (v.lang,)) if x.persona == v.persona)


class MomentRouter(Executor):
    @handler
    async def route(self, batch: MomentBatch, ctx: WorkflowContext[AnalystTask | LensTask | TagTask]) -> None:
        tactical = [p for p in batch.patterns if p.type in TACTICAL]
        player = [p for p in batch.patterns if p.type in PLAYER]
        tags = [p for p in batch.patterns if p.type in TAG_SLOT]
        await ctx.send_message(AnalystTask(tactical, batch.state))
        await ctx.send_message(LensTask(player))
        await ctx.send_message(TagTask(tags, (batch.period, batch.t) if batch.close_period else None))


class TacticalAnalyst(Executor):
    def __init__(self, a: Analysis, by_id: dict[str, Pattern]) -> None:
        super().__init__("tactical_analyst")
        self.builder = Builder(a, "tactical-analyst")
        self.by_id = by_id
        self.last_label: str | None = None

    @handler
    async def analyse(self, task: AnalystTask, ctx: WorkflowContext[Drafts]) -> None:
        for p in task.patterns:
            draft_tactical(self.builder, p, self.by_id)
        self.last_label = draft_state(self.builder, task.state, self.last_label)
        await ctx.send_message(Drafts("tactical_analyst", self.builder.take()))

    async def on_checkpoint_save(self) -> dict:
        return {"last_label": self.last_label}

    async def on_checkpoint_restore(self, state: dict) -> None:
        self.last_label = state.get("last_label")


class PlayerLens(Executor):
    def __init__(self, a: Analysis, by_id: dict[str, Pattern]) -> None:
        super().__init__("player_lens")
        self.builder = Builder(a, "player-lens")
        self.by_id = by_id

    @handler
    async def follow(self, task: LensTask, ctx: WorkflowContext[Drafts]) -> None:
        for p in task.patterns:
            draft_player(self.builder, p, self.by_id)
        await ctx.send_message(Drafts("player_lens", self.builder.take()))


class Editor(Executor):
    def __init__(self) -> None:
        super().__init__("editor")
        self.guard = RepeatGuard()
        self.n = 0
        self.history: list[Draft] = []

    @handler
    async def edit(self, batches: list[Drafts], ctx: WorkflowContext[Edited, CrewNote]) -> None:
        drafts = sorted((d for b in batches for d in b.drafts), key=lambda d: (d.insight.period, d.insight.t))
        kept = []
        for d in drafts:
            if self.guard.allow(d):
                self.n += 1
                d.insight.id = f"in_{self.n}"
                kept.append(d)
        dropped = len(drafts) - len(kept)
        if dropped:
            await ctx.yield_output(CrewNote("editor", "dropped", {"count": dropped}))
        if kept:
            self.history += kept
            await ctx.send_message(Edited(kept))

    async def on_checkpoint_save(self) -> dict:
        return {"n": self.n, "guard": self.guard.save()}

    async def on_checkpoint_restore(self, state: dict) -> None:
        self.n = state.get("n", 0)
        self.guard.restore(state.get("guard", {}))


class Storyteller(Executor):
    """Writes every persona and language. `unreliable` simulates a writer that sometimes misquotes a number."""

    def __init__(self, names: Names, langs: tuple[str, ...], unreliable: float = 0.0, seed: int = 0) -> None:
        super().__init__("storyteller")
        self.names = names
        self.langs = langs
        self.unreliable = unreliable
        self.rng = random.Random(seed)

    def _maybe_slip(self, v: Variant) -> Variant:
        if self.unreliable <= 0 or self.rng.random() >= self.unreliable:
            return v
        body = re.sub(r"\d+", lambda m: str(int(m.group()) + 7), v.body, count=1)
        return Variant(v.insight, v.persona, v.lang, v.headline, body)

    @handler
    async def write(self, edited: Edited, ctx: WorkflowContext[Lines]) -> None:
        for d in edited.drafts:
            describe(d, self.names)
        variants = [self._maybe_slip(v) for d in edited.drafts for v in render_all(d, self.names, self.langs)]
        await ctx.send_message(Lines(edited.drafts, variants, attempt=1))

    @handler
    async def rewrite(self, request: Rewrite, ctx: WorkflowContext[Lines]) -> None:
        by_id = {d.insight.id: d for d in request.drafts}
        fresh = []
        for v, _ in request.failed:
            fresh.append(self._maybe_slip(_template(by_id[v.insight], v, self.names)))
        await ctx.send_message(Lines(request.drafts, request.passed + fresh, attempt=request.attempt + 1))


class Verifier(Executor):
    def __init__(self, names: Names) -> None:
        super().__init__("verifier")
        self.names = names
        self.rejections: list[dict] = []

    @handler
    async def check(self, lines: Lines, ctx: WorkflowContext[Rewrite | Approved, CrewNote]) -> None:
        by_id = {d.insight.id: d for d in lines.drafts}
        passed, failed = [], []
        for v in lines.variants:
            reasons = verify(by_id[v.insight], v, self.names)
            (failed.append((v, reasons)) if reasons else passed.append(v))
        for v, reasons in failed:
            note = {"insight": v.insight, "persona": v.persona, "lang": v.lang, "attempt": lines.attempt,
                    "reasons": reasons, "body": v.body}
            self.rejections.append(note)
            await ctx.yield_output(CrewNote("verifier", "rejected", note))
        if not failed:
            await ctx.send_message(Approved(lines.drafts, passed, lines.fallback))
        elif lines.attempt < MAX_ATTEMPTS:
            await ctx.send_message(Rewrite(lines.drafts, passed, failed, lines.attempt))
        else:
            fallback = set(lines.fallback)
            for v, _ in failed:
                passed.append(_template(by_id[v.insight], v, self.names))
                fallback.add((v.insight, v.persona, v.lang))
            await ctx.yield_output(CrewNote("verifier", "fallback", {"count": len(failed)}))
            await ctx.send_message(Approved(lines.drafts, passed, fallback))


class Producer(Executor):
    def __init__(self, scheduler: Scheduler) -> None:
        super().__init__("producer")
        self.scheduler = scheduler
        self.approved: list[Variant] = []

    @handler
    async def air(self, approved: Approved, ctx: WorkflowContext[Never, PacketBatch]) -> None:
        self.approved += approved.variants
        await ctx.yield_output(PacketBatch(self.scheduler.lines(approved.drafts, approved.variants, approved.fallback)))

    @handler
    async def tag(self, task: TagTask, ctx: WorkflowContext[Never, PacketBatch]) -> None:
        packets = self.scheduler.tags(task.patterns)
        if task.recap is not None:
            packets += self.scheduler.recap(*task.recap)
        await ctx.yield_output(PacketBatch(packets))

    async def on_checkpoint_save(self) -> dict:
        return {"scheduler": self.scheduler.save()}

    async def on_checkpoint_restore(self, state: dict) -> None:
        self.scheduler.restore(state.get("scheduler", {}))


def _is(kind: type):
    return lambda message: isinstance(message, kind)


@dataclass
class Crew:
    workflow: Workflow
    editor: Editor
    verifier: Verifier
    producer: Producer
    names: Names


def build_crew(a: Analysis, langs: tuple[str, ...] = LANGS, unreliable: float = 0.0,
               checkpoints: Path | None = None) -> Crew:
    by_id = {p.id: p for p in a.patterns}
    names = Names(a.md.meta)
    router = MomentRouter("moment_router")
    analyst = TacticalAnalyst(a, by_id)
    lens = PlayerLens(a, by_id)
    editor = Editor()
    storyteller = Storyteller(names, langs, unreliable)
    verifier = Verifier(names)
    producer = Producer(Scheduler(a, names, langs))
    storage = FileCheckpointStorage(checkpoints) if checkpoints else InMemoryCheckpointStorage()
    workflow = (
        WorkflowBuilder(name="insight_crew", start_executor=router, checkpoint_storage=storage,
                        output_from=[producer], intermediate_output_from=[editor, verifier])
        .add_edge(router, analyst, condition=_is(AnalystTask))
        .add_edge(router, lens, condition=_is(LensTask))
        .add_edge(router, producer, condition=_is(TagTask))
        .add_fan_in_edges([analyst, lens], editor)
        .add_edge(editor, storyteller)
        .add_edge(storyteller, verifier)
        .add_edge(verifier, storyteller, condition=_is(Rewrite))
        .add_edge(verifier, producer, condition=_is(Approved))
        .build()
    )
    return Crew(workflow, editor, verifier, producer, names)


def ready_time(p: Pattern) -> float:
    """When a live system would know about a pattern: decoys need the space to be used, chains the shot."""
    return p.t_end + (6.0 if p.type == "decoy_run" else 1.0)


def minute_batches(a: Analysis, step_s: float = 60.0) -> list[MomentBatch]:
    batches = []
    for period in (1, 2):
        start = float(a.md.t[a.md.period == period][0])
        end = float(a.md.t[a.md.period == period][-1])
        edges = [start + k * step_s for k in range(int((end - start) // step_s) + 2)]
        for lo, hi in zip(edges, edges[1:], strict=False):
            last = hi >= end
            patterns = [p for p in a.patterns
                        if p.period == period and (lo <= ready_time(p) < hi or (last and ready_time(p) >= hi))]
            state = [s for s in a.state if s.period == period and lo <= s.t_end < hi]
            batches.append(MomentBatch(period, min(hi, end), patterns, state, close_period=last))
            if last:
                break
    return batches


@dataclass
class CrewRun:
    packets: list[OverlayPacket]
    notes: list[CrewNote]
    timings: dict[str, dict[str, float]]
    runs: int


async def run_match(crew: Crew, a: Analysis, step_s: float = 60.0) -> CrewRun:
    packets: list[OverlayPacket] = []
    notes: list[CrewNote] = []
    timings: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "seconds": 0.0})
    started: dict[str, float] = {}
    batches = minute_batches(a, step_s)
    for batch in batches:
        async for event in crew.workflow.run(batch, stream=True):
            if event.type == "executor_invoked":
                started[event.executor_id] = time.perf_counter()
            elif event.type == "executor_completed" and event.executor_id in started:
                t = timings[event.executor_id]
                t["calls"] += 1
                t["seconds"] += time.perf_counter() - started.pop(event.executor_id)
            elif event.type in ("output", "intermediate"):
                if isinstance(event.data, PacketBatch):
                    packets += event.data.packets
                elif isinstance(event.data, CrewNote):
                    notes.append(event.data)
    packets.sort(key=lambda p: (p.period, p.show_at, p.priority))
    report = {k: {"calls": v["calls"], "ms": round(1000 * v["seconds"], 1)} for k, v in timings.items()}
    return CrewRun(packets, notes, report, len(batches))

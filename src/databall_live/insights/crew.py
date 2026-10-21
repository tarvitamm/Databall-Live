"""The insight crew as a Microsoft Agent Framework workflow.

The router fans each minute of detected patterns out to the tactical analyst and the player lens, which explain them
with a Foundry model and the stats tools. The editor joins their drafts, the storyteller writes every persona and
language, the verifier checks each explanation and line and sends failed lines back for a rewrite, the recapper writes
half-time and full-time panels, and the producer schedules what airs. Every model step has a deadline and a template
fallback, so something accurate always airs on time.
"""

from __future__ import annotations

import asyncio
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
from ..stats.season import Season
from ..stats.state import StateBin
from .analyst import (
    PLAYER,
    TACTICAL,
    Builder,
    Draft,
    RepeatGuard,
    draft_player,
    draft_preview,
    draft_standouts,
    draft_state,
    draft_tactical,
)
from .cache import Cache
from .explainer import PROMPT_VERSION, Explainer
from .foundry import Foundry, ModelOff, Switch
from .producer import TAG_SLOT, Scheduler
from .recapper import RecapWriter
from .storyteller import Names, Variant, describe, describe_lang, render_all
from .text import LANGS
from .tools import MatchTools
from .verifier import verify, verify_explanation, verify_translation
from .writer import ModelWriter

MAX_ATTEMPTS = 3
DEADLINES_S = {"live": {"explain": 15.0, "write": 12.0, "recap": 20.0},
               "batch": {"explain": 120.0, "write": 90.0, "recap": 120.0}}


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
    closing: tuple[int, float] | None = None


@dataclass
class TagTask:
    patterns: list[Pattern]


@dataclass
class RecapTask:
    period: int
    t: float


@dataclass
class RecapLines:
    period: int
    t: float
    texts: dict[tuple[str, str], tuple[str, str]] | None
    source: str


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


def _why(error: BaseException) -> str:
    if isinstance(error, ModelOff):
        return "model off"
    if isinstance(error, TimeoutError):
        return "deadline missed"
    return type(error).__name__


async def explain_all(explainer: Explainer | None, drafts: list[Draft], names: Names,
                      guard: RepeatGuard) -> list[CrewNote]:
    """Template explanations first, then the model where the editor would keep the draft."""
    for d in drafts:
        describe(d, names)
        d.insight.model.analyst = "template"
        d.insight.model.prompt_version = PROMPT_VERSION
    if explainer is None:
        return []
    wanted = [d for d in drafts if guard.allow(d, commit=False)]
    results = await asyncio.gather(*(explainer.explain(d) for d in wanted), return_exceptions=True)
    notes = []
    for d, result in zip(wanted, results, strict=True):
        if isinstance(result, BaseException):
            describe(d, names)
            notes.append(CrewNote(explainer.agent.name, "fallback", {"count": 1, "why": _why(result),
                                                                      "type": d.insight.type}))
    return notes


class MomentRouter(Executor):
    @handler
    async def route(self, batch: MomentBatch,
                    ctx: WorkflowContext[AnalystTask | LensTask | TagTask | RecapTask]) -> None:
        tactical = [p for p in batch.patterns if p.type in TACTICAL]
        player = [p for p in batch.patterns if p.type in PLAYER]
        tags = [p for p in batch.patterns if p.type in TAG_SLOT]
        await ctx.send_message(AnalystTask(tactical, batch.state))
        closing = (batch.period, batch.t) if batch.close_period and batch.period == 1 else None
        await ctx.send_message(LensTask(player, closing))
        await ctx.send_message(TagTask(tags))
        if batch.close_period:
            await ctx.send_message(RecapTask(batch.period, batch.t))


class TacticalAnalyst(Executor):
    def __init__(self, a: Analysis, by_id: dict[str, Pattern], names: Names, guard: RepeatGuard,
                 explainer: Explainer | None, season: Season) -> None:
        super().__init__("tactical_analyst")
        self.builder = Builder(a, "tactical-analyst", season)
        self.by_id = by_id
        self.names = names
        self.guard = guard
        self.explainer = explainer
        self.last_label: str | None = None
        self.previewed = False

    @handler
    async def analyse(self, task: AnalystTask, ctx: WorkflowContext[Drafts, CrewNote]) -> None:
        if not self.previewed:
            self.previewed = True
            draft_preview(self.builder)
        for p in task.patterns:
            draft_tactical(self.builder, p, self.by_id)
        self.last_label = draft_state(self.builder, task.state, self.last_label)
        drafts = self.builder.take()
        for note in await explain_all(self.explainer, drafts, self.names, self.guard):
            await ctx.yield_output(note)
        await ctx.send_message(Drafts("tactical_analyst", drafts))

    async def on_checkpoint_save(self) -> dict:
        return {"last_label": self.last_label, "previewed": self.previewed}

    async def on_checkpoint_restore(self, state: dict) -> None:
        self.last_label = state.get("last_label")
        self.previewed = state.get("previewed", False)


class PlayerLens(Executor):
    def __init__(self, a: Analysis, by_id: dict[str, Pattern], names: Names, guard: RepeatGuard,
                 explainer: Explainer | None, season: Season) -> None:
        super().__init__("player_lens")
        self.builder = Builder(a, "player-lens", season)
        self.by_id = by_id
        self.names = names
        self.guard = guard
        self.explainer = explainer

    @handler
    async def follow(self, task: LensTask, ctx: WorkflowContext[Drafts, CrewNote]) -> None:
        for p in task.patterns:
            draft_player(self.builder, p, self.by_id)
        if task.closing:
            draft_standouts(self.builder, *task.closing)
        drafts = self.builder.take()
        for note in await explain_all(self.explainer, drafts, self.names, self.guard):
            await ctx.yield_output(note)
        await ctx.send_message(Drafts("player_lens", drafts))


class Editor(Executor):
    def __init__(self, guard: RepeatGuard) -> None:
        super().__init__("editor")
        self.guard = guard
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

    def __init__(self, names: Names, langs: tuple[str, ...], writer: ModelWriter | None = None,
                 unreliable: float = 0.0, seed: int = 0) -> None:
        super().__init__("storyteller")
        self.names = names
        self.langs = langs
        self.writer = writer
        self.unreliable = unreliable
        self.rng = random.Random(seed)

    def _maybe_slip(self, v: Variant) -> Variant:
        if self.unreliable <= 0 or self.rng.random() >= self.unreliable:
            return v
        body = re.sub(r"\d+", lambda m: str(int(m.group()) + 7), v.body, count=1)
        return Variant(v.insight, v.persona, v.lang, v.headline, body, v.source)

    async def _write(self, pairs: list[tuple[Draft, list[Variant], list[str] | None]]) -> tuple[list[Variant],
                                                                                                list[CrewNote]]:
        if self.writer is None:
            return [v for _, refs, _ in pairs for v in refs], []
        results = await asyncio.gather(*(self.writer.write(d, refs, feedback) for d, refs, feedback in pairs),
                                       return_exceptions=True)
        out, notes = [], []
        for (d, refs, _), result in zip(pairs, results, strict=True):
            if isinstance(result, BaseException):
                out += refs
                notes.append(CrewNote("storyteller", "fallback", {"count": len(refs), "why": _why(result),
                                                                  "type": d.insight.type}))
            else:
                out += result
                d.insight.model.storyteller = self.writer.foundry.model
        return out, notes

    @handler
    async def write(self, edited: Edited, ctx: WorkflowContext[Lines, CrewNote]) -> None:
        for d in edited.drafts:
            d.insight.model.storyteller = "template"
        pairs = [(d, render_all(d, self.names, self.langs), None) for d in edited.drafts]
        variants, notes = await self._write(pairs)
        for note in notes:
            await ctx.yield_output(note)
        await ctx.send_message(Lines(edited.drafts, [self._maybe_slip(v) for v in variants], attempt=1))

    @handler
    async def rewrite(self, request: Rewrite, ctx: WorkflowContext[Lines, CrewNote]) -> None:
        by_id = {d.insight.id: d for d in request.drafts}
        grouped: dict[str, tuple[list[Variant], list[str]]] = {}
        for v, reasons in request.failed:
            refs, feedback = grouped.setdefault(v.insight, ([], []))
            refs.append(_template(by_id[v.insight], v, self.names))
            feedback += [f"{v.lang} {v.persona}: {r}" for r in reasons]
        pairs = [(by_id[i], refs, feedback) for i, (refs, feedback) in grouped.items()]
        fresh, notes = await self._write(pairs)
        for note in notes:
            await ctx.yield_output(note)
        await ctx.send_message(Lines(request.drafts, request.passed + [self._maybe_slip(v) for v in fresh],
                                     attempt=request.attempt + 1))


class Verifier(Executor):
    def __init__(self, names: Names) -> None:
        super().__init__("verifier")
        self.names = names
        self.rejections: list[dict] = []

    @handler
    async def check(self, lines: Lines, ctx: WorkflowContext[Rewrite | Approved, CrewNote]) -> None:
        by_id = {d.insight.id: d for d in lines.drafts}
        if lines.attempt == 1:
            for d in lines.drafts:
                if d.insight.model.analyst in (None, "template"):
                    continue
                reasons = verify_explanation(d, self.names)
                if reasons:
                    note = {"insight": d.insight.id, "target": "explanation", "attempt": 1, "reasons": reasons,
                            "body": d.insight.mechanism}
                    self.rejections.append(note)
                    await ctx.yield_output(CrewNote("verifier", "rejected", note))
                    describe(d, self.names)
                    d.insight.model.analyst = "template"
            for d in lines.drafts:
                for lang, why in list(d.why.items()):
                    if lang == "en" or why.get("source") == "template":
                        continue
                    reasons = verify_translation(d, lang, self.names)
                    if reasons:
                        note = {"insight": d.insight.id, "target": "explanation", "lang": lang, "attempt": 1,
                                "reasons": reasons, "body": why.get("mechanism", "")}
                        self.rejections.append(note)
                        await ctx.yield_output(CrewNote("verifier", "rejected", note))
                        describe_lang(d, lang, self.names)
        passed, failed = [], []
        for v in lines.variants:
            reasons = verify(by_id[v.insight], v, self.names)
            (failed.append((v, reasons)) if reasons else passed.append(v))
        for v, reasons in failed:
            note = {"insight": v.insight, "target": "line", "persona": v.persona, "lang": v.lang,
                    "attempt": lines.attempt, "reasons": reasons, "body": v.body, "source": v.source}
            self.rejections.append(note)
            await ctx.yield_output(CrewNote("verifier", "rejected", note))
        if not failed:
            await ctx.send_message(Approved(lines.drafts, passed, lines.fallback))
        elif lines.attempt < MAX_ATTEMPTS:
            await ctx.send_message(Rewrite(lines.drafts, passed, failed, lines.attempt))
        else:
            fallback = set(lines.fallback)
            for v, _ in failed:
                t = _template(by_id[v.insight], v, self.names)
                passed.append(Variant(t.insight, t.persona, t.lang, t.headline, t.body, "fallback"))
                fallback.add((v.insight, v.persona, v.lang))
            await ctx.yield_output(CrewNote("verifier", "fallback", {"count": len(failed)}))
            await ctx.send_message(Approved(lines.drafts, passed, fallback))


class Recapper(Executor):
    def __init__(self, scheduler: Scheduler, writer: RecapWriter | None) -> None:
        super().__init__("recapper")
        self.scheduler = scheduler
        self.writer = writer

    @handler
    async def recap(self, task: RecapTask, ctx: WorkflowContext[RecapLines, CrewNote]) -> None:
        references = self.scheduler.recap_references(task.period, task.t)
        texts, source = references, "template"
        if self.writer is not None:
            moment = "half_time" if task.period == 1 else "full_time"
            try:
                texts, source, problems = await self.writer.write(moment, references)
                if problems:
                    await ctx.yield_output(CrewNote("verifier", "rejected", {
                        "target": "recap", "attempt": 1, "reasons": problems, "body": moment}))
            except Exception as error:  # noqa: BLE001
                await ctx.yield_output(CrewNote("recapper", "fallback", {"count": 1, "why": _why(error),
                                                                         "type": "recap"}))
        await ctx.send_message(RecapLines(task.period, task.t, texts, source))


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
        await ctx.yield_output(PacketBatch(self.scheduler.tags(task.patterns)))

    @handler
    async def recap(self, lines: RecapLines, ctx: WorkflowContext[Never, PacketBatch]) -> None:
        await ctx.yield_output(PacketBatch(self.scheduler.recap(lines.period, lines.t, lines.texts, lines.source)))

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
    storyteller: Storyteller
    verifier: Verifier
    producer: Producer
    names: Names
    switch: Switch
    foundry: Foundry | None = None
    cache: Cache | None = None


def build_crew(a: Analysis, langs: tuple[str, ...] = LANGS, unreliable: float = 0.0,
               checkpoints: Path | None = None, foundry: Foundry | None = None, cache: Cache | None = None,
               live: bool = False, season: Season | None = None) -> Crew:
    """A crew over one match. With `foundry` the analysts, storyteller and recapper use the model."""
    by_id = {p.id: p for p in a.patterns}
    names = Names(a.md.meta)
    season = season or Season([])
    switch = Switch()
    cache = cache or Cache()
    explain_tactical = explain_player = writer = recap_writer = None
    if foundry is not None:
        deadline = DEADLINES_S["live" if live else "batch"]
        tools = MatchTools(a, names, season)
        explain_tactical = Explainer(foundry, tools, names, "tactical_analyst", switch, cache, deadline["explain"])
        explain_player = Explainer(foundry, tools, names, "player_lens", switch, cache, deadline["explain"])
        writer = ModelWriter(foundry, names, switch, cache, deadline["write"])
        recap_writer = RecapWriter(foundry, switch, cache, deadline["recap"])
    guard = RepeatGuard()
    scheduler = Scheduler(a, names, langs)
    router = MomentRouter("moment_router")
    analyst = TacticalAnalyst(a, by_id, names, guard, explain_tactical, season)
    lens = PlayerLens(a, by_id, names, guard, explain_player, season)
    editor = Editor(guard)
    storyteller = Storyteller(names, langs, writer, unreliable)
    verifier = Verifier(names)
    recapper = Recapper(scheduler, recap_writer)
    producer = Producer(scheduler)
    storage = FileCheckpointStorage(checkpoints) if checkpoints else InMemoryCheckpointStorage()
    workflow = (
        WorkflowBuilder(name="insight_crew", start_executor=router, checkpoint_storage=storage,
                        output_from=[producer],
                        intermediate_output_from=[analyst, lens, editor, storyteller, verifier, recapper])
        .add_edge(router, analyst, condition=_is(AnalystTask))
        .add_edge(router, lens, condition=_is(LensTask))
        .add_edge(router, producer, condition=_is(TagTask))
        .add_edge(router, recapper, condition=_is(RecapTask))
        .add_fan_in_edges([analyst, lens], editor)
        .add_edge(editor, storyteller)
        .add_edge(storyteller, verifier)
        .add_edge(verifier, storyteller, condition=_is(Rewrite))
        .add_edge(verifier, producer, condition=_is(Approved))
        .add_edge(recapper, producer)
        .build()
    )
    return Crew(workflow, editor, storyteller, verifier, producer, names, switch, foundry, cache)


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


class Timings:
    def __init__(self) -> None:
        self.totals: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "seconds": 0.0})
        self.started: dict[str, float] = {}

    def observe(self, event) -> None:
        if event.type == "executor_invoked":
            self.started[event.executor_id] = time.perf_counter()
        elif event.type == "executor_completed" and event.executor_id in self.started:
            t = self.totals[event.executor_id]
            t["calls"] += 1
            t["seconds"] += time.perf_counter() - self.started.pop(event.executor_id)

    def report(self) -> dict[str, dict[str, float]]:
        return {k: {"calls": v["calls"], "ms": round(1000 * v["seconds"], 1)} for k, v in self.totals.items()}


async def run_batch(crew: Crew, batch: MomentBatch, timings: Timings) -> tuple[list[OverlayPacket], list[CrewNote]]:
    packets: list[OverlayPacket] = []
    notes: list[CrewNote] = []
    async for event in crew.workflow.run(batch, stream=True):
        timings.observe(event)
        if event.type in ("output", "intermediate"):
            if isinstance(event.data, PacketBatch):
                packets += event.data.packets
            elif isinstance(event.data, CrewNote):
                notes.append(event.data)
    return packets, notes


async def run_match(crew: Crew, a: Analysis, step_s: float = 60.0) -> CrewRun:
    packets: list[OverlayPacket] = []
    notes: list[CrewNote] = []
    timings = Timings()
    batches = minute_batches(a, step_s)
    for batch in batches:
        new_packets, new_notes = await run_batch(crew, batch, timings)
        packets += new_packets
        notes += new_notes
    packets.sort(key=lambda p: (p.period, p.show_at, p.priority))
    return CrewRun(packets, notes, timings.report(), len(batches))

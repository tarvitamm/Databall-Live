"""Run the insight crew over a match and save insights, lines, overlay packets and a crew report.

    uv run blindside-insights data/league/m_0106 [--model] [--unreliable 0.2]

With --model the analysts, storyteller and recapper use the Foundry model set in .env, and answers are cached in the
match folder so a second run costs nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from ..contracts import OverlayPacket
from ..stats.analyse import Analysis, analyse, write
from ..stats.season import Season
from .analyst import Draft
from .cache import Cache
from .crew import CrewNote, build_crew, run_match
from .foundry import Foundry, settings
from .storyteller import Variant
from .text import LANGS


@dataclass
class Output:
    analysis: Analysis
    drafts: list[Draft]
    variants: list[Variant]
    rejected: list[dict]
    packets: list[OverlayPacket]
    notes: list[CrewNote]
    report: dict


def run(folder: str | Path, langs: tuple[str, ...] = LANGS, unreliable: float = 0.0,
        checkpoints: Path | None = None, model: bool = False) -> Output:
    return asyncio.run(run_async(Path(folder), langs, unreliable, checkpoints, model))


async def run_async(folder: Path, langs: tuple[str, ...] = LANGS, unreliable: float = 0.0,
                    checkpoints: Path | None = None, model: bool = False) -> Output:
    a = await asyncio.to_thread(analyse, folder)
    foundry, cache = None, Cache(folder / "cache.json")
    if model:
        found = settings()
        if found is None:
            raise SystemExit("Set FOUNDRY_PROJECT_ENDPOINT in .env to use the model")
        foundry = Foundry(found)
    crew = build_crew(a, langs, unreliable=unreliable, checkpoints=checkpoints, foundry=foundry, cache=cache,
                      season=Season.load(folder))
    result = await run_match(crew, a)
    cache.save()
    for d in crew.editor.history:
        d.insight.status = "verified"
    sources = Counter(v.source for v in crew.producer.approved)
    report = {
        "runs": result.runs,
        "insights": len(crew.editor.history),
        "lines": len(crew.producer.approved),
        "rejections": len(crew.verifier.rejections),
        "fallbacks": sum(n.detail["count"] for n in result.notes if n.kind == "fallback"),
        "dropped_as_repeats": sum(n.detail["count"] for n in result.notes if n.kind == "dropped"),
        "packets": len(result.packets),
        "explained_by_model": sum(1 for d in crew.editor.history if d.insight.model.analyst not in (None, "template")),
        "line_sources": dict(sources),
        "model": foundry.report() if foundry else None,
        "executors": result.timings,
    }
    return Output(analysis=a, drafts=crew.editor.history, variants=crew.producer.approved,
                  rejected=crew.verifier.rejections, packets=result.packets, notes=result.notes, report=report)


def save(out: Output, folder: Path) -> None:
    write(out.analysis, folder)
    with (folder / "insights.jsonl").open("w") as f:
        for d in out.drafts:
            f.write(json.dumps({**d.insight.model_dump(exclude_none=True), "facts": d.facts, "tools": d.tools},
                               ensure_ascii=False) + "\n")
    with (folder / "variants.jsonl").open("w") as f:
        for v in out.variants:
            f.write(json.dumps(asdict(v), ensure_ascii=False) + "\n")
    with (folder / "packets.jsonl").open("w") as f:
        for p in out.packets:
            f.write(p.model_dump_json(exclude_none=True) + "\n")
    (folder / "crew.json").write_text(json.dumps({**out.report, "rejected": out.rejected[:50]}, ensure_ascii=False,
                                                 indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--model", action="store_true", help="Use the Foundry model set in .env")
    ap.add_argument("--unreliable", type=float, default=0.0, help="Share of lines the storyteller misquotes")
    ap.add_argument("--checkpoints", type=Path, default=None, help="Folder for workflow checkpoints")
    ap.add_argument("--graph", action="store_true", help="Print the crew as a Mermaid diagram and exit")
    args = ap.parse_args(argv)
    if args.graph:
        from agent_framework import WorkflowViz

        print(WorkflowViz(build_crew(analyse(args.folder)).workflow).to_mermaid())
        return 0
    out = run(args.folder, unreliable=args.unreliable, checkpoints=args.checkpoints, model=args.model)
    save(out, args.folder)
    print(f"{len(out.drafts)} insights {dict(Counter(d.insight.type for d in out.drafts))}")
    print(json.dumps({k: v for k, v in out.report.items() if k not in ("executors", "model")}))
    if out.report["model"]:
        m = out.report["model"]
        print(f"  model {m['model']}: {m['calls']} calls, {m['cached']} cached, {m['timeouts']} timeouts, "
              f"{m['failures']} failures, {m['input_tokens']} in / {m['output_tokens']} out tokens, "
              f"about ${m['cost_usd']:.3f}")
    for name, t in out.report["executors"].items():
        print(f"  {name:17} {t['calls']:4} calls {t['ms']:8.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

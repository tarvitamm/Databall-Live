"""Run the insight crew over a match and save insights, lines, overlay packets and a crew report.

    uv run blindside-insights data/league/m_0106 [--unreliable 0.2]
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
from .analyst import Draft
from .crew import CrewNote, build_crew, run_match
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
        checkpoints: Path | None = None) -> Output:
    a = analyse(folder)
    crew = build_crew(a, langs, unreliable=unreliable, checkpoints=checkpoints)
    result = asyncio.run(run_match(crew, a))
    for d in crew.editor.history:
        d.insight.status = "verified"
    report = {
        "runs": result.runs,
        "insights": len(crew.editor.history),
        "lines": len(crew.producer.approved),
        "rejections": len(crew.verifier.rejections),
        "fallbacks": sum(n.detail["count"] for n in result.notes if n.kind == "fallback"),
        "dropped_as_repeats": sum(n.detail["count"] for n in result.notes if n.kind == "dropped"),
        "packets": len(result.packets),
        "executors": result.timings,
    }
    return Output(analysis=a, drafts=crew.editor.history, variants=crew.producer.approved,
                  rejected=crew.verifier.rejections, packets=result.packets, notes=result.notes, report=report)


def save(out: Output, folder: Path) -> None:
    write(out.analysis, folder)
    with (folder / "insights.jsonl").open("w") as f:
        for d in out.drafts:
            f.write(json.dumps({**d.insight.model_dump(exclude_none=True), "facts": d.facts}) + "\n")
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
    ap.add_argument("--unreliable", type=float, default=0.0, help="Share of lines the storyteller misquotes")
    ap.add_argument("--checkpoints", type=Path, default=None, help="Folder for workflow checkpoints")
    ap.add_argument("--graph", action="store_true", help="Print the crew as a Mermaid diagram and exit")
    args = ap.parse_args(argv)
    if args.graph:
        from agent_framework import WorkflowViz

        print(WorkflowViz(build_crew(analyse(args.folder)).workflow).to_mermaid())
        return 0
    out = run(args.folder, unreliable=args.unreliable, checkpoints=args.checkpoints)
    save(out, args.folder)
    print(f"{len(out.drafts)} insights {dict(Counter(d.insight.type for d in out.drafts))}")
    print(json.dumps({k: v for k, v in out.report.items() if k != "executors"}))
    for name, t in out.report["executors"].items():
        print(f"  {name:17} {t['calls']:4} calls {t['ms']:8.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

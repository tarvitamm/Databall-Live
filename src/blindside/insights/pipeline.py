"""Run the insight crew over an analysed match: analyst, storyteller, verifier, producer.

    uv run blindside-insights data/league/m_0106
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from ..contracts import OverlayPacket
from ..stats.analyse import Analysis, analyse, write
from .analyst import Draft, draft_insights
from .producer import schedule
from .storyteller import Names, Variant, tell
from .text import LANGS
from .verifier import verify


@dataclass
class Output:
    analysis: Analysis
    drafts: list[Draft]
    variants: list[Variant]
    rejected: list[tuple[Variant, list[str]]]
    packets: list[OverlayPacket]


def run(folder: str | Path, langs: tuple[str, ...] = LANGS) -> Output:
    a = analyse(folder)
    drafts = draft_insights(a)
    variants = tell(drafts, a.md.meta, langs)
    names = Names(a.md.meta)
    by_id = {d.insight.id: d for d in drafts}
    passed, rejected = [], []
    for v in variants:
        reasons = verify(by_id[v.insight], v, names)
        (rejected.append((v, reasons)) if reasons else passed.append(v))
    for d in drafts:
        d.insight.status = "verified"
    packets = schedule(a, drafts, passed, names, langs)
    return Output(analysis=a, drafts=drafts, variants=passed, rejected=rejected, packets=packets)


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    args = ap.parse_args(argv)
    out = run(args.folder)
    save(out, args.folder)
    print(f"{len(out.drafts)} insights {dict(Counter(d.insight.type for d in out.drafts))}")
    print(f"{len(out.variants)} lines passed, {len(out.rejected)} rejected, {len(out.packets)} packets")
    for v, reasons in out.rejected[:5]:
        print("rejected:", v.insight, v.persona, v.lang, reasons)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

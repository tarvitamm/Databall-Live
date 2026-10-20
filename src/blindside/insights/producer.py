"""Schedule verified lines and on-ball tags as timed overlay packets, plus half-time and full-time recaps."""

from __future__ import annotations

from ..contracts import OverlayPacket, Pattern
from ..stats.analyse import Analysis
from .analyst import Draft
from .storyteller import Names, Variant, tag_text
from .templates import RECAP
from .text import num

LATENCY_S = 2.0
LOWER_THIRD_S = 12.0
TAG_S = 5.0
MAX_DELAY_S = 20.0
PRIORITY = {"chain": 1, "pressure_shift": 2, "decoy_run": 2, "momentum_swing": 3, "between_lines_gap": 3,
            "counter_press": 3, "overload": 4, "fatigue": 4, "match_state": 4}
VIZ = {"chain": "chain", "pressure_shift": "press_map", "decoy_run": "run_trail", "momentum_swing": "momentum",
       "between_lines_gap": "lines", "counter_press": "press_map", "overload": "overload", "fatigue": "player",
       "match_state": "control_bar"}
TAG_SLOT = {"speed_tag": "player_tag", "match_top_speed": "player_tag", "distance_milestone": "player_tag",
            "recovery_run": "player_tag", "shot_speed": "shot_card", "difficult_pass": "pass_card",
            "line_breaking_pass": "pass_card"}


def _tag_facts(p: Pattern) -> dict:
    m = p.measures
    facts: dict = {"player": p.actor}
    if p.type in ("speed_tag", "match_top_speed", "shot_speed"):
        facts["v"] = m["speed_kmh"]
    elif p.type == "distance_milestone":
        facts["km"] = m["distance_km"]
    elif p.type == "recovery_run":
        facts["m"] = m["distance_back_m"]
    elif p.type == "difficult_pass":
        facts.update(diff=m["difficulty"], m=m["distance_m"])
    elif p.type == "line_breaking_pass":
        facts["n"] = m["lines_broken"]
    return facts


def schedule(a: Analysis, drafts: list[Draft], variants: list[Variant], names: Names,
             langs: tuple[str, ...]) -> list[OverlayPacket]:
    by_id = {d.insight.id: d for d in drafts}
    packets: list[OverlayPacket] = []
    n = 1
    lanes: dict[tuple[str, str], list[OverlayPacket]] = {}
    for v in sorted(variants, key=lambda v: (by_id[v.insight].insight.period, by_id[v.insight].insight.t)):
        ins = by_id[v.insight].insight
        show = ins.t + LATENCY_S
        lane = lanes.setdefault((v.persona, v.lang), [])
        prev = next((p for p in reversed(lane) if p.period == ins.period), None)
        if prev is not None and show < prev.expires_at:
            if prev.expires_at + 0.5 - show > MAX_DELAY_S:
                continue
            show = prev.expires_at + 0.5
        packet = OverlayPacket(
            packet=f"op_{n}", match=a.md.meta.match, insight=ins.id, persona=v.persona, lang=v.lang,
            slot="lower_third", priority=PRIORITY.get(ins.type, 4), show_at=round(show, 1),
            expires_at=round(show + LOWER_THIRD_S, 1), period=ins.period,
            text={"headline": v.headline, "body": v.body},
            data={"type": ins.type, "teams": ins.entities.get("teams", []), "players": ins.entities.get("players", []),
                  "significance": ins.significance, "confidence": ins.confidence, "signals": ins.signals},
            viz={"kind": VIZ.get(ins.type, "none"), "window": list(ins.evidence.window or (ins.t - 10, ins.t))})
        lane.append(packet)
        packets.append(packet)
        n += 1
    for p in a.patterns:
        if p.type not in TAG_SLOT or p.actor is None:
            continue
        facts = _tag_facts(p)
        for lang in langs:
            packets.append(OverlayPacket(
                packet=f"op_{n}", match=a.md.meta.match, persona="fan", lang=lang, slot=TAG_SLOT[p.type], priority=5,
                show_at=round(p.t_start + 0.5, 1), expires_at=round(p.t_start + 0.5 + TAG_S, 1), period=p.period,
                text={"headline": tag_text(p.type, facts, lang, names)},
                data={"type": p.type, "kind": "tag", "teams": [p.team], "players": [p.actor], "pattern": p.id}))
            n += 1
    packets += recaps(a, drafts, variants, langs, start_id=n)
    packets.sort(key=lambda p: (p.period, p.show_at, p.priority))
    return packets


def recap_text(a: Analysis, drafts: list[Draft], variants: list[Variant], lang: str, period: int, t: float,
               moment: str) -> tuple[str, str]:
    md = a.md
    home, away = md.codes
    done = lambda e: e["period"] < period or (e["period"] == period and e["t"] <= t)  # noqa: E731
    goals = [e["team"] for e in md.events if e["type"] == "goal" and done(e)]
    xg = {code: 0.0 for code in md.codes}
    events = {e["id"]: e for e in md.events}
    for s in a.shots:
        if done(events[s.event]):
            xg[md.codes[s.team]] += s.xg or 0.0
    seen = [d for d in drafts if d.insight.period < period or (d.insight.period == period and d.insight.t <= t)]
    top = sorted(seen, key=lambda d: -d.insight.significance)[:3]
    fan = {(v.insight, v.lang): v.headline for v in variants if v.persona == "fan"}
    moments = "; ".join(fan[(d.insight.id, lang)] for d in sorted(top, key=lambda d: (d.insight.period, d.insight.t))
                        if (d.insight.id, lang) in fan) or "-"
    names = {c.code: c.name.split()[0] for c in (md.meta.home, md.meta.away)}
    body = RECAP[lang]["body"].format(home=names[home], away=names[away], hs=goals.count(home), as_=goals.count(away),
                                      hx=num(xg[home], lang, 1), ax=num(xg[away], lang, 1), moments=moments)
    return RECAP[lang][moment], body


def recaps(a: Analysis, drafts: list[Draft], variants: list[Variant], langs: tuple[str, ...],
           start_id: int) -> list[OverlayPacket]:
    out = []
    n = start_id
    for period, moment in ((1, "half_time"), (2, "full_time")):
        t = float(a.md.t[a.md.period == period][-1])
        for lang in langs:
            headline, body = recap_text(a, drafts, variants, lang, period, t, moment)
            for persona in ("analyst", "fan"):
                out.append(OverlayPacket(
                    packet=f"op_{n}", match=a.md.meta.match, persona=persona, lang=lang, slot="panel", priority=1,
                    show_at=round(t + 1.0, 1), expires_at=round(t + 61.0, 1), period=period,
                    text={"headline": headline, "body": body}, data={"type": "recap", "kind": moment}))
                n += 1
    return out

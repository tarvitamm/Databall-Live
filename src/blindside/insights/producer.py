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


class Scheduler:
    """Keeps one lane per persona and language so lower thirds never overlap, and remembers what aired."""

    def __init__(self, a: Analysis, names: Names, langs: tuple[str, ...]) -> None:
        self.a = a
        self.names = names
        self.langs = langs
        self.n = 0
        self.lanes: dict[str, tuple[int, float]] = {}
        self.aired: list[dict] = []

    def _id(self) -> str:
        self.n += 1
        return f"op_{self.n}"

    def lines(self, drafts: list[Draft], variants: list[Variant],
              fallback: set[tuple[str, str, str]]) -> list[OverlayPacket]:
        by_id = {d.insight.id: d for d in drafts}
        out = []
        for v in sorted(variants, key=lambda v: (by_id[v.insight].insight.period, by_id[v.insight].insight.t)):
            ins = by_id[v.insight].insight
            show = ins.t + LATENCY_S
            lane = f"{v.persona}:{v.lang}"
            period, busy_until = self.lanes.get(lane, (0, -1e9))
            if period == ins.period and show < busy_until:
                if busy_until + 0.5 - show > MAX_DELAY_S:
                    continue
                show = busy_until + 0.5
            self.lanes[lane] = (ins.period, show + LOWER_THIRD_S)
            out.append(OverlayPacket(
                packet=self._id(), match=self.a.md.meta.match, insight=ins.id, persona=v.persona, lang=v.lang,
                slot="lower_third", priority=PRIORITY.get(ins.type, 4), show_at=round(show, 1),
                expires_at=round(show + LOWER_THIRD_S, 1), period=ins.period,
                text={"headline": v.headline, "body": v.body},
                data={"type": ins.type, "teams": ins.entities.get("teams", []),
                      "players": ins.entities.get("players", []), "significance": ins.significance,
                      "confidence": ins.confidence, "signals": ins.signals},
                viz={"kind": VIZ.get(ins.type, "none"), "window": list(ins.evidence.window or (ins.t - 10, ins.t))},
                fallback=(v.insight, v.persona, v.lang) in fallback))
            if v.persona == "fan":
                self.aired.append({"insight": ins.id, "lang": v.lang, "period": ins.period, "t": ins.t,
                                   "headline": v.headline, "significance": ins.significance})
        return out

    def tags(self, patterns: list[Pattern]) -> list[OverlayPacket]:
        out = []
        for p in patterns:
            if p.type not in TAG_SLOT or p.actor is None:
                continue
            facts = _tag_facts(p)
            for lang in self.langs:
                out.append(OverlayPacket(
                    packet=self._id(), match=self.a.md.meta.match, persona="fan", lang=lang, slot=TAG_SLOT[p.type],
                    priority=5, show_at=round(p.t_start + 0.5, 1), expires_at=round(p.t_start + 0.5 + TAG_S, 1),
                    period=p.period, text={"headline": tag_text(p.type, facts, lang, self.names)},
                    data={"type": p.type, "kind": "tag", "teams": [p.team], "players": [p.actor], "pattern": p.id}))
        return out

    def recap(self, period: int, t: float) -> list[OverlayPacket]:
        moment = "half_time" if period == 1 else "full_time"
        out = []
        for lang in self.langs:
            headline, body = self.recap_text(lang, period, t, moment)
            for persona in ("analyst", "fan"):
                out.append(OverlayPacket(
                    packet=self._id(), match=self.a.md.meta.match, persona=persona, lang=lang, slot="panel",
                    priority=1, show_at=round(t + 1.0, 1), expires_at=round(t + 61.0, 1), period=period,
                    text={"headline": headline, "body": body}, data={"type": "recap", "kind": moment}))
        return out

    def recap_text(self, lang: str, period: int, t: float, moment: str) -> tuple[str, str]:
        md = self.a.md
        home, away = md.codes
        done = lambda p, et: p < period or (p == period and et <= t)  # noqa: E731
        goals = [e["team"] for e in md.events if e["type"] == "goal" and done(e["period"], e["t"])]
        xg = {code: 0.0 for code in md.codes}
        events = {e["id"]: e for e in md.events}
        for s in self.a.shots:
            e = events[s.event]
            if done(e["period"], e["t"]):
                xg[md.codes[s.team]] += s.xg or 0.0
        seen = [x for x in self.aired if x["lang"] == lang and done(x["period"], x["t"])]
        top = sorted(seen, key=lambda x: -x["significance"])[:3]
        moments = "; ".join(x["headline"] for x in sorted(top, key=lambda x: (x["period"], x["t"]))) or "-"
        teams = self.names.team
        body = RECAP[lang]["body"].format(home=teams[home], away=teams[away], hs=goals.count(home),
                                          as_=goals.count(away), hx=num(xg[home], lang, 1), ax=num(xg[away], lang, 1),
                                          moments=moments)
        return RECAP[lang][moment], body

    def save(self) -> dict:
        return {"n": self.n, "lanes": {k: list(v) for k, v in self.lanes.items()}, "aired": self.aired}

    def restore(self, state: dict) -> None:
        self.n = state.get("n", 0)
        self.lanes = {k: (v[0], v[1]) for k, v in state.get("lanes", {}).items()}
        self.aired = list(state.get("aired", []))

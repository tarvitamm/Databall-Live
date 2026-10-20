"""Render each insight for every persona and language from templates."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import MatchMetadata
from .analyst import Draft
from .templates import DRIVER, OUTCOME, PASSES, SERVED, TAGS, T
from .text import POSITION, SIDE, num, surname

PERSONAS = ("analyst", "fan", "player_focus")
PLAYER_KEYS = {"runner", "defender", "benef", "shooter", "decoy", "player", "focus"}
DECIMALS = {"pa": 1, "pb": 1, "la": 0, "lb": 0, "d": 0, "xg": 2, "sec": 0, "passes": 0, "tpm": 1, "under": 0,
            "ca": 0, "cb": 0, "poss": 0, "terr": 0, "n": 0, "s": 1, "gap": 0, "a": 0, "pct": 0, "now": 1,
            "early": 1, "fn": 0, "v": 1, "km": 0, "m": 0, "diff": 1}
AND = {"en": "and", "es": "y", "et": "ja"}


@dataclass
class Variant:
    insight: str
    persona: str
    lang: str
    headline: str
    body: str


class Names:
    def __init__(self, meta: MatchMetadata) -> None:
        self.team = {t.code: t.name.split()[0] for t in (meta.home, meta.away)}
        self.player = {p.id: surname(p.name) for t in (meta.home, meta.away) for p in t.lineup + t.bench}


def localize(facts: dict, lang: str, names: Names) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in facts.items():
        if key in ("team", "opp"):
            out[key] = names.team.get(value, value)
        elif key in PLAYER_KEYS:
            out[key] = names.player.get(value, value)
        elif key == "leaders":
            people = [names.player.get(v, v) for v in value]
            out[key] = f" {AND[lang]} ".join(people) if people else "-"
        elif key == "pos":
            out[key] = POSITION[lang].get(value, value)
        elif key == "side":
            out[key] = SIDE[lang].get(value, value)
        elif key == "drivers":
            out[key] = ", ".join(DRIVER[lang].get(v, v) for v in value) or "-"
        elif key == "outcome":
            out[key] = OUTCOME[lang].get(value, value)
        elif key == "passes":
            one, many = PASSES[lang]
            out[key] = (one if int(value) == 1 else many).format(n=int(value))
        elif key == "served":
            out[key] = SERVED[lang] if value else ""
        elif isinstance(value, int | float):
            out[key] = num(float(value), lang, DECIMALS.get(key, 0))
        else:
            out[key] = str(value)
    return out


def render(d: Draft, persona: str, lang: str, names: Names) -> Variant | None:
    by_persona = T[d.key][lang]
    if persona == "player_focus" and persona not in by_persona:
        return None
    if persona == "player_focus" and "focus" not in d.facts and "runner" not in d.facts and "decoy" not in d.facts:
        return None
    headline, body = by_persona.get(persona, by_persona["fan"])
    values = localize(d.facts, lang, names)
    return Variant(d.insight.id, persona, lang, headline.format(**values), body.format(**values))


def tag_text(kind: str, facts: dict, lang: str, names: Names) -> str:
    return TAGS[kind][lang].format(**localize(facts, lang, names))


def tell(drafts: list[Draft], meta: MatchMetadata, langs: tuple[str, ...]) -> list[Variant]:
    names = Names(meta)
    out = []
    for d in drafts:
        for lang in langs:
            for persona in PERSONAS:
                v = render(d, persona, lang, names)
                if v is not None:
                    out.append(v)
        en = render(d, "fan", "en", names)
        en_analyst = render(d, "analyst", "en", names)
        d.insight.claim = en.headline if en else ""
        d.insight.mechanism = en_analyst.body if en_analyst else ""
        d.insight.consequence = en.body if en else ""
    return out

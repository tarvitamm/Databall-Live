"""Check every rendered line against the facts it was built from before it can air."""

from __future__ import annotations

import re

from .analyst import Draft
from .storyteller import Names, Variant, localize
from .templates import T

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
MAX_HEADLINE = 48
MAX_BODY = 150


def _template_numbers(d: Draft, v: Variant) -> set[str]:
    by_persona = T[d.key][v.lang]
    headline, body = by_persona.get(v.persona, by_persona["fan"])
    return set(NUMBER.findall(re.sub(r"\{[^}]*\}", "", headline + " " + body)))


def verify(d: Draft, v: Variant, names: Names) -> list[str]:
    """Reasons the line must not air. An empty list means it passed."""
    reasons = []
    text = f"{v.headline} {v.body}"
    if "{" in text or "}" in text:
        reasons.append("unfilled placeholder")
    allowed = set(_template_numbers(d, v))
    for value in localize(d.facts, v.lang, names).values():
        allowed.update(NUMBER.findall(value))
    for found in NUMBER.findall(text):
        if found not in allowed:
            reasons.append(f"number {found} is not in the facts")
    mentioned = {pid for pid, name in names.player.items() if re.search(rf"\b{re.escape(name)}\b", text)}
    allowed_players = set(d.insight.entities.get("players", []))
    allowed_players |= {v for k, v in d.facts.items() if isinstance(v, str) and v in names.player}
    allowed_players |= set(d.facts.get("leaders", []))
    same_name = {pid for pid in mentioned if any(names.player[q] == names.player[pid] for q in allowed_players)}
    for pid in mentioned - allowed_players - same_name:
        reasons.append(f"names {pid}, who is not part of this insight")
    if len(v.headline) > MAX_HEADLINE:
        reasons.append(f"headline is {len(v.headline)} characters")
    if len(v.body) > MAX_BODY:
        reasons.append(f"body is {len(v.body)} characters")
    return reasons

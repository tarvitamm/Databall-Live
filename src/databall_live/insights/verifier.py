"""Check every rendered line against the facts it was built from before it can air."""

from __future__ import annotations

import re

from .analyst import Draft
from .storyteller import Names, Variant, localize
from .templates import T

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
AHEAD_WORDS = {"en": r"\b(ahead|in front|lead|leads|leading)\b",
               "es": r"\b(adelant\w*|por delante|ventaja|ganando)\b",
               "et": r"\b(juhtima|juhib|juhtimas|eduseis\w*|edu)\b",
               "de": r"\b(führ\w*|vorn\w*)\b",
               "fr": r"\b(mène\w*|avantage|devant)\b"}
LEVEL_WORDS = {"en": r"\b(level|levels|equalis\w*|equaliz\w*|draw|tied?)\b",
               "es": r"\b(empat\w*|iguala\w*)\b",
               "et": r"\b(viik\w*|viigi\w*|egaliseeri\w*)\b",
               "de": r"\b(ausgleich\w*|gleichstand|unentschieden)\b",
               "fr": r"\b(égalis\w*|égalité)\b"}
MAX_HEADLINE = 48
MAX_BODY = 150
MAX_ANALYST_BODY = 180


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
    seen = _fact_numbers(d) | (d.seen if v.persona == "analyst" else set())
    for found in NUMBER.findall(text):
        if found not in allowed and not _supported(found, seen):
            reasons.append(f"number {found} is not in the facts")
    reasons += _score_words(d, v, text)
    mentioned = {pid for pid, name in names.player.items() if re.search(rf"\b{re.escape(name)}\b", text)}
    allowed_players = set(d.insight.entities.get("players", []))
    allowed_players |= {v for k, v in d.facts.items() if isinstance(v, str) and v in names.player}
    allowed_players |= set(d.facts.get("leaders", []))
    same_name = {pid for pid in mentioned if any(names.player[q] == names.player[pid] for q in allowed_players)}
    for pid in mentioned - allowed_players - same_name:
        if not re.search(rf"\b{re.escape(names.player[pid])}\b", d.seen_text):
            reasons.append(f"names {pid}, who is not part of this insight")
    if len(v.headline) > MAX_HEADLINE:
        reasons.append(f"headline is {len(v.headline)} characters")
    if len(v.body) > (MAX_ANALYST_BODY if v.persona == "analyst" else MAX_BODY):
        reasons.append(f"body is {len(v.body)} characters")
    return reasons


MAX_CLAIM = 140
MAX_MECHANISM = 320
MAX_CONSEQUENCE = 200
WINDOWS = {5.0, 10.0}


def _score_words(d: Draft, v: Variant, text: str) -> list[str]:
    """A goal line may only describe the score the way the facts say it stands."""
    state = d.facts.get("state")
    if state is None or v.lang not in AHEAD_WORDS:
        return []
    lower = text.lower()
    reasons = []
    if state not in ("ahead", "extends") and re.search(AHEAD_WORDS[v.lang], lower):
        reasons.append(f"says the scorers are ahead, but the goal {state}")
    if state != "level" and re.search(LEVEL_WORDS[v.lang], lower):
        reasons.append(f"says the score is level, but the goal {state}")
    return reasons


def _value(raw: str) -> float:
    return float(raw.replace(",", "."))


def _supported(found: str, allowed: set[float]) -> bool:
    """A number may be rounded from something the agent saw, never invented."""
    value = _value(found)
    allowed = {abs(a) for a in allowed}
    decimals = len(found.replace(",", ".").split(".")[1]) if "." in found.replace(",", ".") else 0
    return any(abs(round(a, decimals) - value) < 1e-9 or abs(a - value) < 1e-9 for a in allowed)


def _fact_numbers(d: Draft) -> set[float]:
    out: set[float] = set()
    for value in list(d.facts.values()) + list(d.insight.signals.values()):
        for v in value if isinstance(value, list) else [value]:
            if isinstance(v, int | float) and not isinstance(v, bool):
                out.add(float(v))
            elif isinstance(v, str):
                out.update(_value(x) for x in NUMBER.findall(v))
    out.add(float(int(d.insight.t // 60) + 1))
    return out


def verify_explanation(d: Draft, names: Names) -> list[str]:
    """Reasons an analyst's explanation cannot be used. It may only cite what the facts and its tools showed."""
    ins = d.insight
    text = f"{ins.claim} {ins.mechanism} {ins.consequence}"
    reasons = []
    allowed = _fact_numbers(d) | d.seen | WINDOWS
    for found in NUMBER.findall(text):
        if not _supported(found, allowed):
            reasons.append(f"number {found} is not in the facts or tool results")
    known = set(ins.entities.get("players", [])) | {v for v in d.facts.values() if isinstance(v, str)}
    known |= set(d.facts.get("leaders", []))
    for pid, name in names.player.items():
        if re.search(rf"\b{re.escape(name)}\b", text) and pid not in known and not re.search(
                rf"\b{re.escape(name)}\b", d.seen_text):
            reasons.append(f"names {name}, who is not in the facts or tool results")
    for label, value, limit in (("claim", ins.claim, MAX_CLAIM), ("mechanism", ins.mechanism, MAX_MECHANISM),
                                ("consequence", ins.consequence, MAX_CONSEQUENCE)):
        if not value.strip():
            reasons.append(f"{label} is empty")
        elif len(value) > limit:
            reasons.append(f"{label} is {len(value)} characters")
    return reasons


def verify_numbers(text: str, allowed: set[float]) -> list[str]:
    return [f"number {found} is not in the facts" for found in NUMBER.findall(text) if not _supported(found, allowed)]


def verify_translation(d: Draft, lang: str, names: Names) -> list[str]:
    """A translated explanation may only carry numbers and players from the English one and the facts."""
    why = d.why.get(lang, {})
    text = f"{why.get('claim', '')} {why.get('mechanism', '')} {why.get('consequence', '')}"
    en = f"{d.insight.claim} {d.insight.mechanism} {d.insight.consequence}"
    allowed = _fact_numbers(d) | {_value(x) for x in NUMBER.findall(en)} | WINDOWS
    reasons = [f"number {x} is not in the explanation" for x in NUMBER.findall(text) if not _supported(x, allowed)]
    for name in names.player.values():
        if re.search(rf"\b{re.escape(name)}\b", text) and not re.search(rf"\b{re.escape(name)}\b", en):
            reasons.append(f"names {name}, who is not in the explanation")
    limits = (("claim", MAX_CLAIM), ("mechanism", MAX_MECHANISM + 60), ("consequence", MAX_CONSEQUENCE + 40))
    for label, limit in limits:
        if not why.get(label, "").strip():
            reasons.append(f"{label} is empty")
        elif len(why[label]) > limit:
            reasons.append(f"{label} is {len(why[label])} characters")
    return reasons

"""The storyteller as a Foundry agent: persona and language lines, grounded in an insight's facts.

The template line for each persona and language is passed as a correct reference. The model may phrase it better but
may not add facts: the verifier checks every number and name before anything airs.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from .analyst import Draft
from .cache import Cache
from .explainer import PROMPT_VERSION, clean, parse
from .foundry import Foundry, ModelOff, Switch
from .storyteller import Names, Variant, localize
from .verifier import MAX_BODY, MAX_HEADLINE

LANG_NAME = {"en": "English", "es": "Spanish", "et": "Estonian", "de": "German", "fr": "French"}
PERSONA_STYLE = {
    "analyst": "for analysts and coaches: precise and comparative. Lead with the mechanism, keep the key numbers with "
               "units, and compare with the season average or the previous value whenever the facts include one",
    "fan": "for fans following live on their phone: make them feel it. Lead with what is at stake for the club or the "
           "player, then the reason in plain words. If the facts include a season best, a record, a season total or a "
           "league rank, put it up front. At most one number per sentence, no jargon",
    "player_focus": "for a fan who follows this one player: what the player just did, why it mattered, and how it "
                    "compares with the player's own season when the facts allow. Warm and specific",
}
INSTRUCTIONS = f"""You write on-screen graphics and app notifications for live association football (soccer).
For each requested language and persona, rewrite the reference line into a line people want to read.
Rules:
- Use only facts in the reference lines and the facts list. The analyst's explanation tells you why it happened; use it
  for the cause, never for extra numbers.
- Copy every number and name exactly as written in that language's facts. Spanish and Estonian use a decimal comma.
- Never add numbers, players, clubs or events.
- Only call something a record, a best, the most, the fastest or a first when the facts say so.
- Describe the score only with the score sentence in the facts (state). Never call a goal a lead, an equaliser or a
  winner in any other way.
- The facts are authoritative. Season totals in the facts already include today's match.
- Headlines are hooks: specific, active, no questions, no clickbait.
- Headline at most {MAX_HEADLINE - 10} characters. Body at most {MAX_BODY - 30} characters, one or two short sentences.
  Count the characters: longer lines are rejected.
- Write natively in each language, as a broadcaster from that country would. No translationese.
- Also put the analyst's explanation (claim, mechanism, consequence) into every requested language other than English
  under "why": the same facts and numbers, natural football language, decimal commas where the language uses them.
- Never use dashes as punctuation. No emojis, no hashtags.
Return JSON only."""


class Line(BaseModel):
    lang: str
    persona: str
    headline: str
    body: str


class Why(BaseModel):
    lang: str
    claim: str
    mechanism: str
    consequence: str


class Lines(BaseModel):
    lines: list[Line]
    why: list[Why] = []


class ModelWriter:
    def __init__(self, foundry: Foundry, names: Names, switch: Switch, cache: Cache, timeout_s: float) -> None:
        self.foundry = foundry
        self.names = names
        self.switch = switch
        self.cache = cache
        self.timeout_s = timeout_s
        self.agent = foundry.agent("storyteller", INSTRUCTIONS, Lines)

    def _prompt(self, d: Draft, wanted: list[Variant], feedback: list[str] | None) -> str:
        langs = sorted({v.lang for v in wanted})
        facts = {lang: localize(d.facts, lang, self.names) for lang in langs}
        refs = [{"lang": v.lang, "persona": v.persona, "style": PERSONA_STYLE[v.persona],
                 "reference_headline": v.headline, "reference_body": v.body} for v in wanted]
        why = {"claim": d.insight.claim, "mechanism": d.insight.mechanism, "consequence": d.insight.consequence}
        parts = [f"Insight type: {d.insight.type}.",
                 f"Analyst's explanation: {json.dumps(why, ensure_ascii=False)}",
                 f"Facts per language: {json.dumps(facts, ensure_ascii=False)}",
                 f"Write these lines: {json.dumps(refs, ensure_ascii=False)}"]
        if feedback:
            parts.append("Your previous lines were rejected for these reasons. Fix them: " + "; ".join(feedback))
        parts.append("Languages: " + ", ".join(f"{k} = {LANG_NAME[k]}" for k in langs))
        return "\n".join(parts)

    async def write(self, d: Draft, wanted: list[Variant], feedback: list[str] | None = None) -> list[Variant]:
        """Lines for the wanted persona and language pairs. Raises to fall back to the references."""
        pairs = [(v.lang, v.persona) for v in wanted]
        key = Cache.key("lines", [PROMPT_VERSION, self.foundry.model, INSTRUCTIONS, d.key, d.facts,
                                  d.insight.mechanism, pairs, feedback])
        found = self.cache.get(key) if self.switch.mode != "off" else None
        source = "cached"
        if found:
            self.foundry.usage[self.agent.name].cached += 1
        elif self.switch.mode != "live":
            raise ModelOff()
        else:
            response = await self.foundry.run(self.agent, self._prompt(d, wanted, feedback), self.timeout_s)
            parsed = parse(response, Lines)
            found = {"lines": [x.model_dump() for x in parsed.lines], "why": [x.model_dump() for x in parsed.why]}
            self.cache.put(key, found)
            source = "model"
        langs = {v.lang for v in wanted} - {"en"}
        for why in found.get("why", []):
            if why["lang"] in langs and not feedback:
                d.why[why["lang"]] = {"claim": clean(why["claim"]), "mechanism": clean(why["mechanism"]),
                                      "consequence": clean(why["consequence"]), "lang": why["lang"], "source": source}
        by_key = {(x["lang"], x["persona"]): x for x in found["lines"]}
        out = []
        for ref in wanted:
            line = by_key.get((ref.lang, ref.persona))
            if line is None:
                out.append(ref)
            else:
                out.append(Variant(ref.insight, ref.persona, ref.lang, clean(line["headline"]), clean(line["body"]),
                                   source))
        return out

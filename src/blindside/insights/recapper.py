"""The recapper as a Foundry agent: half-time and full-time panels written from what actually aired."""

from __future__ import annotations

import json

from pydantic import BaseModel

from .cache import Cache
from .explainer import PROMPT_VERSION, clean, parse
from .foundry import Foundry, ModelOff, Switch
from .verifier import NUMBER, verify_numbers
from .writer import LANG_NAME

MAX_RECAP_HEADLINE = 48
MAX_RECAP_BODY = 300
INSTRUCTIONS = f"""You write the half-time or full-time recap panel for a live association football (soccer) broadcast.
For each requested language and persona, write a headline and a short recap from the reference recap.
Rules:
- Use only the score, xG and key moments in the reference. Copy numbers exactly as written for that language.
- Headline at most {MAX_RECAP_HEADLINE - 8} characters. Body at most {MAX_RECAP_BODY - 40} characters, two or three
  sentences.
- analyst: names the pattern that shaped the half. fan: vivid and plain, tells the story of the half.
- Write natively in each language. Never use dashes as punctuation. No emojis.
Return JSON only."""


class RecapLine(BaseModel):
    lang: str
    persona: str
    headline: str
    body: str


class Recap(BaseModel):
    lines: list[RecapLine]


Texts = dict[tuple[str, str], tuple[str, str]]


def _allowed(reference: tuple[str, str]) -> set[float]:
    return {float(x.replace(",", ".")) for x in NUMBER.findall(" ".join(reference))}


class RecapWriter:
    def __init__(self, foundry: Foundry, switch: Switch, cache: Cache, timeout_s: float) -> None:
        self.foundry = foundry
        self.switch = switch
        self.cache = cache
        self.timeout_s = timeout_s
        self.agent = foundry.agent("recapper", INSTRUCTIONS, Recap)

    async def write(self, moment: str, references: Texts) -> tuple[Texts, str, list[str]]:
        """Recap lines for every reference, the source, and why any line fell back to its reference."""
        refs = [{"lang": lang, "language": LANG_NAME[lang], "persona": persona, "reference_headline": h,
                 "reference_body": b} for (lang, persona), (h, b) in sorted(references.items())]
        key = Cache.key("recap", [PROMPT_VERSION, self.foundry.model, INSTRUCTIONS, moment, refs])
        found = self.cache.get(key) if self.switch.mode != "off" else None
        source = "cached"
        if found:
            self.foundry.usage[self.agent.name].cached += 1
        elif self.switch.mode != "live":
            raise ModelOff()
        else:
            prompt = f"Moment: {moment.replace('_', ' ')}.\nWrite these lines: {json.dumps(refs, ensure_ascii=False)}"
            response = await self.foundry.run(self.agent, prompt, self.timeout_s)
            found = {"lines": [x.model_dump() for x in parse(response, Recap).lines]}
            self.cache.put(key, found)
            source = "model"
        out: Texts = dict(references)
        problems = []
        for line in found["lines"]:
            pair = (line["lang"], line["persona"])
            if pair not in references:
                continue
            headline, body = clean(line["headline"]), clean(line["body"])
            reasons = verify_numbers(f"{headline} {body}", _allowed(references[pair]))
            if len(headline) > MAX_RECAP_HEADLINE or len(body) > MAX_RECAP_BODY:
                reasons.append("too long")
            if reasons:
                problems.append(f"{pair[0]} {pair[1]}: {'; '.join(reasons)}")
            else:
                out[pair] = (headline, body)
        return out, source, problems

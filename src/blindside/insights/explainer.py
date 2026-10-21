"""The tactical analyst and the player lens as Foundry agents.

Each reads a moment the detectors flagged, checks it with the stats tools and explains the cause behind it. The
template explanation is the baseline the agent improves on, and the fallback when the model is cut or too slow.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from .analyst import Draft
from .cache import Cache
from .foundry import Foundry, ModelOff, Switch
from .storyteller import Names
from .text import minute
from .tools import MatchTools, ToolLog

PROMPT_VERSION = "crew-v3"
ROLE = {
    "tactical_analyst": "tactical analyst. You explain team patterns: pressing, momentum, gaps between the lines, "
                        "overloads, counter-pressing, who controls the game, and the story before kick-off.",
    "player_lens": "player analyst. You explain one player's story: decoy runs that drag defenders away, the moves "
                   "that led to a shot, goals, season-best sprints, records and fatigue.",
}
INSTRUCTIONS = """You are the {role}
You work on a live association football (soccer) broadcast. A rule-based detector flagged the moment below. Explain it
for the producer and for analysts: what happened, the off-the-ball mechanism that caused it, and what it led to or what
to watch next.
Rules:
- Call tools to check the numbers before you write. Cite only values from the moment facts or tool results. You may
  round them.
- Name players by surname, and only players that appear in the facts or tool results. Name clubs by their name.
- The baseline explanation is correct but plain. Improve it with the cause, not with new claims.
- Use season_record when it sharpens the point, for example a press well above the club's season average or a
  player's best game of the season. Say so only when the numbers show it.
- claim: one sentence, at most 110 characters. mechanism: at most two sentences and 280 characters, with the key
  numbers. consequence: one sentence, at most 170 characters.
- Plain English, present tense, no hype, no speculation about injuries or private matters.
- Never use dashes as punctuation.
Return JSON only."""


class Explanation(BaseModel):
    claim: str
    mechanism: str
    consequence: str


def clean(text: str) -> str:
    for dash in (" \u2014 ", "\u2014", " \u2013 ", "\u2013"):
        text = text.replace(dash, ", ")
    return " ".join(text.split())


def parse(response, schema: type[BaseModel]):
    value = getattr(response, "value", None)
    return value if isinstance(value, schema) else schema.model_validate_json(response.text)


class Explainer:
    def __init__(self, foundry: Foundry, tools: MatchTools, names: Names, role: str, switch: Switch, cache: Cache,
                 timeout_s: float) -> None:
        self.foundry = foundry
        self.tools = tools
        self.names = names
        self.switch = switch
        self.cache = cache
        self.timeout_s = timeout_s
        self.instructions = INSTRUCTIONS.format(role=ROLE[role])
        self.agent = foundry.agent(role, self.instructions, Explanation, effort="low")

    def _prompt(self, d: Draft) -> str:
        ins = d.insight
        players = {pid: self.names.player.get(pid, pid) for pid in ins.entities.get("players", [])}
        return "\n".join([
            f"Moment: {ins.type} ({d.key}) at minute {minute(ins.t)} of half {ins.period}.",
            f"Clubs: {json.dumps(self.names.team)}",
            f"Players: {json.dumps(players, ensure_ascii=False)}",
            f"Facts: {json.dumps(d.facts, default=str, ensure_ascii=False)}",
            f"Signals: {json.dumps(ins.signals)}",
            f"Detector pattern ids: {ins.evidence.patterns}",
            f"Baseline claim: {ins.claim}",
            f"Baseline mechanism: {ins.mechanism}",
            f"Baseline consequence: {ins.consequence}",
        ])

    def _apply(self, d: Draft, found: dict) -> None:
        d.insight.claim = clean(found["claim"])
        d.insight.mechanism = clean(found["mechanism"])
        d.insight.consequence = clean(found["consequence"])
        d.seen = set(found["seen"])
        d.seen_text = found["seen_text"]
        d.tools = found["tools"]
        d.insight.model.analyst = self.foundry.model

    async def explain(self, d: Draft) -> str:
        """Fill the draft's claim, mechanism and consequence. Returns "model" or "cached"; raises to fall back."""
        ins = d.insight
        key = Cache.key("explain", [PROMPT_VERSION, self.foundry.model, self.instructions, ins.type, d.key,
                                    ins.period, ins.t, d.facts])
        found = self.cache.get(key) if self.switch.mode != "off" else None
        if found:
            self.foundry.usage[self.agent.name].cached += 1
            self._apply(d, found)
            return "cached"
        if self.switch.mode != "live":
            raise ModelOff()
        log = ToolLog()
        response = await self.foundry.run(self.agent, self._prompt(d), self.timeout_s,
                                          tools=self.tools.bind((ins.period, ins.t), log))
        e = parse(response, Explanation)
        found = {**e.model_dump(), "seen": sorted(log.numbers()), "seen_text": log.text(), "tools": log.summary()}
        self.cache.put(key, found)
        self._apply(d, found)
        return "model"

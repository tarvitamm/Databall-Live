"""Microsoft Foundry models for the crew: settings, one shared client, deadlines and usage accounting.

Locally the Azure CLI login is used; in Azure Container Apps the app's managed identity. No keys anywhere.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

PRICE_PER_M = {"gpt-5-mini": (0.25, 2.0)}
Mode = Literal["live", "cache", "off"]


def load_env(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


@dataclass
class Settings:
    endpoint: str
    model: str


def settings() -> Settings | None:
    load_env()
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    return Settings(endpoint, os.environ.get("FOUNDRY_MODEL", "gpt-5-mini")) if endpoint else None


class ModelOff(Exception):
    """The model is switched off or the answer is not cached, so the caller falls back to templates."""


@dataclass
class Usage:
    calls: int = 0
    failures: int = 0
    timeouts: int = 0
    cached: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    def as_dict(self, model: str) -> dict:
        price_in, price_out = PRICE_PER_M.get(model, (0.0, 0.0))
        cost = (self.input_tokens * price_in + self.output_tokens * price_out) / 1e6
        mean = self.seconds / self.calls if self.calls else 0.0
        return {"calls": self.calls, "failures": self.failures, "timeouts": self.timeouts, "cached": self.cached,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "mean_s": round(mean, 2), "cost_usd": round(cost, 4)}


@dataclass
class Switch:
    """Shared by every agent in one crew: live calls, cached answers only, or templates only."""

    mode: Mode = "live"


def _credential():
    from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential

    if os.environ.get("IDENTITY_ENDPOINT"):
        return ManagedIdentityCredential(client_id=os.environ.get("AZURE_CLIENT_ID"))
    return AzureCliCredential()


@dataclass
class Foundry:
    settings: Settings
    concurrency: int = 12
    usage: dict[str, Usage] = field(default_factory=lambda: defaultdict(Usage))

    def __post_init__(self) -> None:
        from agent_framework.foundry import FoundryChatClient

        self.model = self.settings.model
        self.client = FoundryChatClient(project_endpoint=self.settings.endpoint, model=self.model,
                                        credential=_credential())
        self.gate = asyncio.Semaphore(self.concurrency)

    def agent(self, name: str, instructions: str, response_format: type, effort: str = "minimal"):
        from agent_framework import Agent

        return Agent(client=self.client, name=name, instructions=instructions,
                     default_options={"response_format": response_format, "reasoning": {"effort": effort}})

    async def run(self, agent, prompt: str, timeout_s: float, tools: list | None = None):
        """One agent call under a deadline. Raises on any failure so the caller can fall back."""
        u = self.usage[agent.name]
        start = time.perf_counter()
        async with self.gate:
            try:
                response = await asyncio.wait_for(agent.run(prompt, tools=tools), timeout_s)
            except TimeoutError:
                u.timeouts += 1
                raise
            except Exception:
                u.failures += 1
                raise
            finally:
                u.seconds += time.perf_counter() - start
        u.calls += 1
        tokens = getattr(response, "usage_details", None) or {}
        u.input_tokens += int(tokens.get("input_token_count") or 0)
        u.output_tokens += int(tokens.get("output_token_count") or 0)
        return response

    def report(self) -> dict:
        per_agent = {name: u.as_dict(self.model) for name, u in self.usage.items()}
        total = Usage()
        for u in self.usage.values():
            for key in ("calls", "failures", "timeouts", "cached", "input_tokens", "output_tokens", "seconds"):
                setattr(total, key, getattr(total, key) + getattr(u, key))
        return {"model": self.model, "agents": per_agent, **total.as_dict(self.model)}

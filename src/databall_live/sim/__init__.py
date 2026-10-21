"""Synthetic match simulator: events, 10 Hz tracking and hidden tactical truth."""

from .clubs import CLUBS
from .engine import SIM_VERSION, MatchEngine

__all__ = ["CLUBS", "SIM_VERSION", "MatchEngine"]

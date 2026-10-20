"""Names, positions and number formatting for each supported language."""

from __future__ import annotations

LANGS = ("en", "es", "et")

POSITION = {
    "en": {"GK": "goalkeeper", "RB": "right-back", "LB": "left-back", "RCB": "centre-back", "LCB": "centre-back",
           "DM": "holding midfielder", "RDM": "holding midfielder", "LDM": "holding midfielder",
           "RCM": "midfielder", "LCM": "midfielder", "AM": "playmaker", "RM": "right midfielder",
           "LM": "left midfielder", "RW": "right winger", "LW": "left winger", "ST": "striker", "RS": "striker",
           "LS": "striker"},
    "es": {"GK": "portero", "RB": "lateral derecho", "LB": "lateral izquierdo", "RCB": "central", "LCB": "central",
           "DM": "pivote", "RDM": "pivote", "LDM": "pivote", "RCM": "centrocampista", "LCM": "centrocampista",
           "AM": "mediapunta", "RM": "interior derecho", "LM": "interior izquierdo", "RW": "extremo derecho",
           "LW": "extremo izquierdo", "ST": "delantero", "RS": "delantero", "LS": "delantero"},
    "et": {"GK": "väravavaht", "RB": "paremkaitsja", "LB": "vasakkaitsja", "RCB": "keskkaitsja", "LCB": "keskkaitsja",
           "DM": "kaitsev poolkaitsja", "RDM": "kaitsev poolkaitsja", "LDM": "kaitsev poolkaitsja",
           "RCM": "poolkaitsja", "LCM": "poolkaitsja", "AM": "ründav poolkaitsja", "RM": "parem poolkaitsja",
           "LM": "vasak poolkaitsja", "RW": "paremääre", "LW": "vasakääre", "ST": "ründaja", "RS": "ründaja",
           "LS": "ründaja"},
}

SIDE = {"en": {"left": "left", "right": "right", "centre": "centre"},
        "es": {"left": "izquierda", "right": "derecha", "centre": "centro"},
        "et": {"left": "vasakul", "right": "paremal", "centre": "keskel"}}


def num(value: float, lang: str, decimals: int = 0) -> str:
    text = f"{value:.{decimals}f}"
    return text.replace(".", ",") if lang in ("es", "et") else text


def minute(t: float) -> str:
    return f"{int(t // 60) + 1}'"


def surname(full_name: str) -> str:
    return full_name.split()[-1]

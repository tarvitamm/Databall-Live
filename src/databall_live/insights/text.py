"""Names, positions and number formatting for each supported language."""

from __future__ import annotations

LANGS = ("en", "es", "de", "fr", "et")
# German and French go to the model in a call of their own, so lines already cached for the first three stay valid
MODEL_GROUPS = (("en", "es", "et"), ("de", "fr"))

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
    "de": {"GK": "Torwart", "RB": "Rechtsverteidiger", "LB": "Linksverteidiger", "RCB": "Innenverteidiger",
           "LCB": "Innenverteidiger", "DM": "Sechser", "RDM": "Sechser", "LDM": "Sechser", "RCM": "Mittelfeldspieler",
           "LCM": "Mittelfeldspieler", "AM": "Spielmacher", "RM": "Mittelfeldspieler", "LM": "Mittelfeldspieler",
           "RW": "Rechtsaußen", "LW": "Linksaußen", "ST": "Stürmer", "RS": "Stürmer", "LS": "Stürmer"},
    "fr": {"GK": "gardien", "RB": "latéral droit", "LB": "latéral gauche", "RCB": "défenseur central",
           "LCB": "défenseur central", "DM": "milieu défensif", "RDM": "milieu défensif", "LDM": "milieu défensif",
           "RCM": "milieu", "LCM": "milieu", "AM": "meneur de jeu", "RM": "milieu droit", "LM": "milieu gauche",
           "RW": "ailier droit", "LW": "ailier gauche", "ST": "attaquant", "RS": "attaquant", "LS": "attaquant"},
}

SIDE = {"en": {"left": "on the left", "right": "on the right", "centre": "through the middle"},
        "es": {"left": "por la izquierda", "right": "por la derecha", "centre": "por el centro"},
        "et": {"left": "vasakul", "right": "paremal", "centre": "keskel"},
        "de": {"left": "auf links", "right": "auf rechts", "centre": "durch die Mitte"},
        "fr": {"left": "à gauche", "right": "à droite", "centre": "dans l’axe"}}


def num(value: float, lang: str, decimals: int = 0) -> str:
    text = f"{value:.{decimals}f}"
    return text if lang == "en" else text.replace(".", ",")


def minute(t: float) -> str:
    return f"{int(t // 60) + 1}'"


def surname(full_name: str) -> str:
    return full_name.split()[-1]

"""Province name matching. Every source spells provinces differently; all of them are mapped to the official code."""
from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd

from src import config

_PREFIXES = re.compile(r"^(?:ខេត្ត|រាជធានី|ក្រុង|province of|province|khaet|khett|krong|capital|city of|municipality)\s*", re.I)
_SUFFIXES = re.compile(r"\s*(?:province|capital|municipality|city)$", re.I)


def normalise(name) -> str:
    """Lower-case, drop admin words, spaces, hyphens and accents; unify Khmer subscript ta/da."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    text = str(name).strip()
    text = _SUFFIXES.sub("", _PREFIXES.sub("", text))
    text = text.replace("្ដ", "្ត").replace("ី", "ិ")  # common Khmer spelling variants
    text = text.casefold().replace("é", "e")
    return re.sub(r"[\s\-_.'’]", "", text)


def province_table() -> pd.DataFrame:
    """The name-matching table, one row per province."""
    rows = [{"pro_code": code, "iso_3166_2": iso, "province": portal, "name_census": census, "name_khmer": khmer,
             "aliases": aliases} for code, iso, portal, census, khmer, aliases in config.PROVINCES]
    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def _lookup() -> dict:
    table = {}
    for code, iso, portal, census, khmer, aliases in config.PROVINCES:
        for variant in [portal, census, khmer, iso, str(code), *aliases.split("|")]:
            key = normalise(variant)
            if key:
                table[key] = portal
    return table


def match_province(name) -> str | None:
    """Return the portal spelling of a province, or None when the name is not recognised."""
    key = normalise(name)
    if not key:
        return None
    return _lookup().get(key)  # ISO codes such as "KH-12" normalise to "kh12", which is in the table


def code_for(province: str) -> int | None:
    lookup = {portal: code for code, _, portal, *_ in config.PROVINCES}
    return lookup.get(province)


def write_matching_table(path=None) -> pd.DataFrame:
    table = province_table()
    table.to_csv(path or config.PROVINCE_NAMES, index=False, encoding="utf-8")
    return table

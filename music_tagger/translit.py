"""Transliteration, per language.

A title is not transliterated by guessing at it. `romanize_title` looks at the
*script* of the title and picks one of two paths:

  kanji / hiragana  ->  romanize locally (pykakasi for Japanese, RR for Korean)
  katakana only     ->  use the official Latin title supplied by the caller

Katakana is the script Japan borrows foreign words with, so a katakana-only
title is almost always an English word the artist wrote down phonetically -
often with a pun that no romanizer can reproduce (ビリミリオン reads
"birimirion" but the release is "Billimillion"). For those, the caller passes
the real Latin title and we use it; romanizing would be wrong twice over.

The `latin_alias` argument is that supplied title. It comes from the *same
album's* tracklist on Deezer, matched by track position, so it is not a guess.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .scripts import compose

_KAKASI = None


def _kakasi():
    global _KAKASI
    if _KAKASI is None:
        from pykakasi import Kakasi

        _KAKASI = Kakasi()
    return _KAKASI


def _pykakasi_romaji(text: str) -> str:
    import unicodedata

    # NFKC turns fullwidth punctuation (！) into ASCII so it does not end up
    # stranded on its own as a separate token.
    text = unicodedata.normalize("NFKC", text or "")
    parts = [x["hepburn"] for x in _kakasi().convert(text)]
    joined = " ".join(p for p in parts if p.strip())
    joined = re.sub(r"\s+([,.!?;:%'\")\]}])", r"\1", joined)
    joined = re.sub(r"([({'\[])\s+", r"\1", joined)
    return _clean_collapse(joined)


def _korean_romanization(text: str) -> str:
    if not _romanizer_available("ko"):
        return text
    try:
        from korean_romanizer.romanizer import Romanizer

        return Romanizer(text).romanize()
    except Exception:
        return text


def _clean_collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def romanize_text(text: str, lang: str = "ja") -> str:
    """Romanize `text` in place. No title-resolution logic here."""
    if not text:
        return text
    if lang == "ja":
        return _clean_collapse(_pykakasi_romaji(text))
    if lang == "ko":
        return _clean_collapse(_korean_romanization(text))
    return text


def _title_case_first(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def romanize_title(
    title: str,
    *,
    lang: str = "ja",
    latin_alias: str | None = None,
    keep_original: bool = False,
) -> str:
    """Return the Latin form of `title` using the script it is written in.

    latin_alias : the official Latin title for *this* track, as published.
                  Only consulted when the title is katakana-only.
    """
    comp = compose(title)
    if not comp.has_cjk and not comp.has_korean:
        return _clean_collapse(title)

    if lang == "ko":
        return _korean_romanization(title)

    # Katakana-only: a loanword. Prefer the published Latin title, and fall
    # back to romanizing only when no alias was supplied or it is empty.
    if comp.is_katakana_only:
        alias = _clean_collapse(latin_alias or "")
        if alias and not re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", alias):
            return alias

    romaji = _pykakasi_romaji(title)
    if keep_original and comp.has_japanese:
        # caller asked to keep the original visible alongside the romanization
        return f"{_title_case_first(romaji)} ({title})"
    return _title_case_first(romaji)


def needs_latin_alias(text: str) -> bool:
    """True when a katakana-only title would benefit from the published name."""
    return compose(text).is_katakana_only


@lru_cache(maxsize=None)
def _romanizer_available(lang: str) -> bool:
    try:
        if lang == "ja":
            import pykakasi  # noqa: F401
        elif lang == "ko":
            import korean_romanizer  # noqa: F401
        return True
    except ImportError:
        return False
    return False


SUPPORTED_LANGUAGES = ("ja", "ko")

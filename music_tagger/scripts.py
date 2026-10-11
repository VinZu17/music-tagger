"""Script (writing-system) detection.

Everything else keys off this: whether a title needs transliterating, which
transliterator to use, and whether a romanization should be trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HIRAGANA = re.compile(r"[\u3040-\u309f\u309b\u309c]")
KATAKANA = re.compile(r"[\u30a0-\u30ff]")
KANJI = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
CYRILLIC = re.compile(r"[\u0400-\u04ff]")
ARABIC = re.compile(r"[\u0600-\u06ff]")
THAI = re.compile(r"[\u0e00-\u0e7f]")
GREEK = re.compile(r"[\u0370-\u03ff]")
HEBREW = re.compile(r"[\u0590-\u05ff]")
LATIN = re.compile(r"[A-Za-z]")
DIGITS = re.compile(r"[0-9]")


@dataclass(frozen=True)
class Composition:
    """Count of characters per script inside one string."""

    hiragana: int = 0
    katakana: int = 0
    kanji: int = 0
    hangul: int = 0
    cyrillic: int = 0
    arabic: int = 0
    thai: int = 0
    greek: int = 0
    hebrew: int = 0
    latin: int = 0
    digits: int = 0

    @property
    def cjk(self) -> int:
        """Hiragana + katakana + kanji: the Japanese scripts."""
        return self.hiragana + self.katakana + self.kanji

    @property
    def has_cjk(self) -> bool:
        return self.cjk > 0

    @property
    def has_japanese(self) -> bool:
        """Kanji or hiragana - content written natively in Japanese.

        Katakana alone is excluded: it is the script Japan uses for
        loanwords, so a katakana-only title is usually an English word and
        should be looked up rather than romanized.
        """
        return self.hiragana > 0 or self.kanji > 0

    @property
    def has_korean(self) -> bool:
        return self.hangul > 0

    @property
    def is_katakana_only(self) -> bool:
        """Katakana present, no native Japanese content at all."""
        return self.katakana > 0 and self.hiragana == 0 and self.kanji == 0

    @property
    def is_latin_only(self) -> bool:
        return self.latin > 0 and self.cjk == 0 and self.hangul == 0 and not self.other

    @property
    def other(self) -> int:
        return self.cyrillic + self.arabic + self.thai + self.greek + self.hebrew

    @property
    def script(self) -> str:
        """One of: latin, katakana, japanese, korean, cyrillic, arabic, thai,
        greek, hebrew, other, digits."""
        if self.cyrillic:
            return "cyrillic"
        if self.arabic:
            return "arabic"
        if self.thai:
            return "thai"
        if self.greek:
            return "greek"
        if self.hebrew:
            return "hebrew"
        if self.hangul:
            return "korean"
        if self.hiragana or self.kanji:
            return "japanese"
        if self.katakana:
            return "katakana"
        if self.latin:
            return "latin"
        return "digits"


def compose(text: str) -> Composition:
    """Count how much of `text` belongs to each writing system."""
    counts = {f: 0 for f in ("hiragana", "katakana", "kanji", "hangul", "cyrillic",
                             "arabic", "thai", "greek", "hebrew", "latin", "digits")}
    for ch in text or "":
        for name, rx in (("hiragana", HIRAGANA), ("katakana", KATAKANA), ("kanji", KANJI),
                         ("hangul", HANGUL), ("cyrillic", CYRILLIC), ("arabic", ARABIC),
                         ("thai", THAI), ("greek", GREEK), ("hebrew", HEBREW),
                         ("latin", LATIN), ("digits", DIGITS)):
            if rx.match(ch):
                counts[name] += 1
                break
    return Composition(**counts)

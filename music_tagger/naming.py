"""Filename parsing and formatting.

Two directions: taking the name a downloader left behind and pulling an artist
and a title out of it, and building a clean name back up again.

The parser is deliberately permissive. Downloaders produce names like
"01 - Artist - Title (Official MV).mp4", "Artist「Title」.flac" and
"01. Title.mp3"; none of those are worth a dedicated rule, so the parser
strips known noise, splits on the strongest separator it finds, and returns
what it found along with a confidence so the caller can fall back to a
provider search when the parse looks untrustworthy.
"""

from __future__ import annotations

import re
import unicodedata

LEADING_INDEX = re.compile(r"^(\d{1,4})\s*[-–_.]\s*")
QUOTED = re.compile(r"['‘’“”\"](.+)['‘’“”\"]")
ALIAS_PARENS = re.compile(r"[（(【\[]([^)）】\]]{1,40})[)）】\]]")
BRACKET_BLOCK = re.compile(r"\s*[\[【]([^\]】]*)[\]】]")
CHANNEL_SUFFIX = re.compile(r"\s[｜|]\s.*$")
FEAT = re.compile(r"\s*\((?:feat|ft|featuring)\.?\s+[^)]+\)", re.I)
FROM_CLAUSE = re.compile(r"\bfrom\s+(.+)$", re.I)
LATIN_IN_PARENS = re.compile(r"[（(【\[]([^)）】\]]*[A-Za-z][^)）】\]]*)[)）】\]]")

NOISE_TAIL = [
    r"exclusive\s+performance\s+video", r"official\s+performance\s+video",
    r"performance\s+ver\.?\s*\d*", r"performance\s+version",
    r"official\s+lyrics?\s+video", r"official\s+m\s*[/・·]\s*v", r"official\s+mv",
    r"official\s+music\s+video", r"lyrics?\s+video", r"music\s+video",
    r"m\s*[/・·]\s*v", r"#\d+[a-z0-9]*", r"\bvisual\s+izer\b", r"\bpv\b",
    r"\bmv\b", r"\bteaser\b", r"\btrailer\b", r"\blive\b", r"\bdance\s+practice\b",
    r"\bpreview\b", r"\bofficial\b",
]
NOISE_RE = re.compile(r"(?:^|[\s|/·・])+(" + "|".join(NOISE_TAIL) + r")\s*$", re.I)
TRIM = " \t|/·・-,;"

SEPARATORS = [" - ", " – ", " ― ", " ｜ ", "｜", " · ", "・", " / ", "_", " -"]
STYLES = ("artist-title", "title-artist")


def fold(text: str) -> str:
    """Casefolded, punctuation-free. Non-Latin letters are kept."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]+", " ", text)).strip()


def strip_non_latin(text: str) -> str:
    return fold(re.sub(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]", " ", text or ""))


def title_variants(title: str) -> list[str]:
    """Matching keys for a title: as-is, plus any bracketed/parenthesised part.

    A title written as 魔法の絨毯 (Mahou no Jutan) will match a provider whose
    title is "Mahou no Jutan" through the bracketed variant, which is why the
    original string is not the only key.
    """
    out: list[str] = []
    for chunk in (title, *ALIAS_PARENS.findall(title or "")):
        for key in (fold(chunk), strip_non_latin(chunk)):
            if key and key not in out:
                out.append(key)
    return [k for k in out if len(k) >= 2]


def parse(filename: str) -> dict:
    """Pull an index, artist and title out of a music filename."""
    stem = re.sub(r"\.(mp3|flac|m4a|mp4|ogg|opus|wav|ape|wma|aac|alac)$", "",
                  filename or "", flags=re.I)
    raw = unicodedata.normalize("NFKC", stem)

    index = ""
    m = LEADING_INDEX.match(raw)
    if m:
        index, raw = m.group(1), raw[m.end():]

    raw = CHANNEL_SUFFIX.sub("", raw)
    for _ in range(6):
        before = raw
        raw = raw.strip(TRIM)
        raw = NOISE_RE.sub("", raw)
        if raw == before:
            break
    body = raw.strip(TRIM)

    artist, title, how = "", body, "no-artist"
    q = QUOTED.search(body)
    if q:
        title, artist, how = q.group(1), body[:q.start()], "quoted"
    else:
        for sep in SEPARATORS:
            if sep in body:
                head, tail = body.rsplit(sep, 1)
                artist, title, how = head, tail, f"sep:{sep.strip()}"
                break

    fm = FROM_CLAUSE.search(artist or "")
    if fm:
        artist = fm.group(1).strip()
    else:
        fm = FROM_CLAUSE.search(title or "")
        if fm:
            artist, title = fm.group(1).strip(), title[:fm.start()].strip(TRIM)

    artist = re.sub(r"\s{2,}", " ", artist.strip(TRIM))
    title = title.strip(TRIM) or body

    # "Song (2).mp3" is what a downloader calls a duplicate; a trailing bare
    # number in parentheses is not part of the title.
    dup = ""
    dm = re.search(r"\s*\((\d{1,3})\)\s*$", title)
    if dm and dm.group(1) != "0":
        dup, title = dm.group(1), title[:dm.start()].strip(TRIM)

    return {
        "index": index,
        "artist": artist,
        "title": title,
        "duplicate": dup,
        "how": how,
        "aliases": [fold(a) for a in ALIAS_PARENS.findall(artist)
                    if not a.isascii() or not a.strip().isalpha()],
    }


def sanitize(part: str) -> str:
    """Make one filename component safe on every filesystem."""
    s = (part or "").replace("/", " & ")
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" .")
    return s.encode("utf-8")[:90].decode("utf-8", "ignore").strip()


ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def format_name(artist: str, title: str, style: str = "artist-title",
                ext: str = "mp3", suffix: str = "") -> str:
    """Build a filename. `style` is one of STYLES."""
    if style not in STYLES:
        raise ValueError(f"unknown name style {style!r}; expected one of {STYLES}")
    stem = title + (f" ({suffix})" if suffix else "")
    a, t = sanitize(artist), sanitize(stem)
    name = f"{a} - {t}.{ext}" if style == "artist-title" else f"{t} - {a}.{ext}"
    return name[:180]


def display_title(title: str, artist: str) -> str:
    """Drop a "(feat. X)" that is already named in the artist field."""
    m = FEAT.search(title or "")
    if m:
        names = [fold(p) for p in re.findall(r"[A-Za-z][\w.'-]*", m.group(0))]
        names = [n for n in names if n not in ("feat", "ft", "featuring")]
        if names and all(n in fold(artist) for n in names):
            return FEAT.sub("", title).strip()
    return title


ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

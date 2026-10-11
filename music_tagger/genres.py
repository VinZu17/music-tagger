"""Genre normalisation.

Providers return genre in their own language: iTunes Japan says ロック, Spotify
says nothing at all, MusicBrainz says rock. A library that mixes those is
unsortable, so everything is folded into a small set of readable Latin labels,
prefixed with the region when the genre is region-specific enough to warrant
it ("J-Rock", "K-Pop").
"""

from __future__ import annotations

import re

# Native-script label -> the Latin label the same genre carries internationally.
NATIVE = {
    # Japanese
    "ロック": "Rock", "ロックン": "Rock'n'Roll", "進化論的ロックン": "Prog Rock",
    "ハードロック": "Hard Rock", "ヘヴィメタル": "Heavy Metal", "メタル": "Metal",
    "ポップ": "Pop", "J-POP": "Pop", "シティポップ": "City Pop",
    "アイドル": "Idol", "ラップ": "Rap", "HIP-Hop": "Hip-Hop", "HIPHop": "Hip-Hop",
    "Future Bass": "Future Bass", "EDM": "EDM", "ハウス": "House",
    "クラスター": "Cluster", "パンク": "Punk", "アニメソング": "Anime",
    "ドラム&ベース": "Drum & Bass", "レゲエ": "Reggae", "ソウル": "Soul",
    "ジャズ": "Jazz", "フォーク": "Folk", "演歌": "Enka", "歌謡曲": "Kayokyoku",
    # Korean
    "발라드": "Ballad", "댄스": "Dance", "트로트": "Trot", "인디": "Indie",
    "랩/힙합": "Hip-Hop", "알앤비": "R&B", "록/메탈": "Rock", "포크": "Folk",
    # Chinese
    "流行": "Pop", "摇滚": "Rock", "民谣": "Folk", "说唱": "Rap",
    "电子": "EDM", "爵士": "Jazz", "古典": "Classical", "轻音乐": "Easy Listening",
    # Russian
    "Поп": "Pop", "Рок": "Rock", "Рэп": "Rap", "Электроника": "EDM",
    "Шансон": "Chanson", "Метал": "Metal",
}

# Regions whose music is commonly catalogued with a regional prefix.
REGION_PREFIX = {"ja": "J", "ko": "K", "zh": "C"}

# Genres that already carry their region in the name and must not be prefixed again.
ALREADY_REGIONAL = re.compile(r"^K-|^J-|^C-|K-Pop|J-Pop|C-Pop|J-Rock|K-Rock", re.I)

# Genres that are global by nature - prefixing them would be wrong.
GLOBAL = {"pop", "rock", "hip-hop", "rap", "r&b", "edm", "electronic", "house",
          "techno", "jazz", "classical", "folk", "metal", "punk", "reggae",
          "soul", "funk", "blues", "country", "ambient", "latin", "indie",
          "alternative", "disco", "gospel", "salsa", "afrobeats"}


def normalize(genre: str, lang: str = "") -> str:
    """Return a readable Latin genre label for `genre`.

    `lang` is an ISO-639-1 hint ("ja", "ko", "zh"). A genre that arrives in a
    native script came from that region's store, so its region is known and the
    regional prefix is applied (ロック -> J-Rock). A genre that arrives already
    Latin is only prefixed when it is region-flavoured music, because "Rock"
    alone could be from anywhere.
    """
    raw = (genre or "").strip()
    if not raw:
        return ""
    native = NATIVE.get(raw)
    label = (native or raw).strip()
    key = label.casefold()

    if ALREADY_REGIONAL.match(label):
        return label

    if native is not None:  # native-script input: the store, and so the region, is known
        prefix = REGION_PREFIX.get(lang, "")
        return f"{prefix}-{label}" if prefix else label

    if key in GLOBAL:
        return label
    if key in REGIONAL_FLAVOURED or _looks_regional(label):
        prefix = REGION_PREFIX.get(lang, "")
        return f"{prefix}-{label}" if prefix else label
    return label


REGIONAL_FLAVOURED = {"idol", "enka", "kayokyoku", "trot", "city pop", "visual kei",
                      "anime", "tongyo"}


def _looks_regional(label: str) -> bool:
    """Genres that only make sense inside a regional scene."""
    return any(word in label.casefold() for word in
               ("idol", "enka", "trot", "visual kei", "city pop", "anime", "gugak"))

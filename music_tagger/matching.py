"""Scoring a provider candidate against what the filename claims."""

from __future__ import annotations

import difflib

from .naming import fold, strip_non_latin, title_variants


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def title_score(variants: list[str], candidate_title: str) -> float:
    """Best similarity between any query variant and the provider's title.

    Comparison happens on the folded form, which keeps CJK letters - comparing
    only the Latin part would make a Japanese or Korean title impossible to
    match against itself. The Latin-only form is checked as well, because that
    is how a romanized query meets a provider that spells the title out.

    A romanized title often sits *inside* a differently-spelled provider title
    ("Do the Dance" inside "Billyeoon Goyangi (Do the Dance)"). Containment
    counts as a match for that reason, but only for variants long enough not
    to be a false positive.
    """
    target = fold(candidate_title)
    target_latin = strip_non_latin(target)
    best = 0.0
    for v in variants:
        best = max(best, _sim(v, target))
        if target_latin:
            best = max(best, _sim(strip_non_latin(v), target_latin))
        if len(v) >= 4 and v in target:
            best = max(best, 0.90)
    return best


def _name_sim(a: str, b: str) -> float:
    """Similarity between two artist names.

    difflib alone over-credits names that merely share letters ("someone else"
    vs "babymonster" scores 0.43) which is enough to slip a wrong artist past
    the threshold. When two names share no whole word, that is treated as the
    disagreement it is.
    """
    ratio = _sim(a, b)
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and not (ta & tb):
        # no whole word in common - "someone else" vs "babymonster" shares
        # letters but is a different artist, so do not let difflib's char-level
        # overlap carry it over the line
        return min(ratio, 0.25)
    return ratio


def score(candidate: dict, artist: str, title: str, aliases: list[str] | None = None) -> float:
    """0..1 confidence that `candidate` is the track the filename describes."""
    variants = title_variants(title) or [fold(title)]
    t = title_score(variants, candidate.get("title", ""))
    if not artist:
        return round(t, 4)
    keys = [fold(artist), *(aliases or [])]
    keys = [k for k in keys if k]
    if not keys:
        return round(t, 4)
    a = max(_name_sim(k, fold(candidate.get("artist", ""))) for k in keys)
    weighted = round(0.68 * t + 0.32 * a, 4)
    # An artist the filename does not agree with at all caps the score: an
    # exact title match with a different artist is usually a cover or a
    # same-named song, and should not be applied unattended.
    if a < 0.40:
        weighted = min(weighted, 0.5)
    return weighted


ACCEPT = 0.72


def pick(candidates: dict[str, list[dict]], artist: str, title: str,
         aliases: list[str] | None = None,
         accept: float = ACCEPT, order: tuple[str, ...] | None = None) -> tuple[dict | None, str]:
    """Pick the best candidate, honouring provider priority.

    Returns (candidate, source_name); (None, "") when nothing clears `accept`.
    """
    order = order or tuple(candidates)
    for source in order:
        best, top = None, 0.0
        for c in candidates.get(source, []):
            s = c.get("score", 0.0) or score(c, artist, title, aliases)
            if s > top:
                best, top = c, s
        if best is not None and top >= accept:
            chosen = dict(best)
            chosen["score"] = top
            return chosen, source
    return None, ""

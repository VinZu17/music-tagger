"""The pipeline: filename in, tagged and renamed file out.

    parse the filename -> resolve metadata -> decide the Latin title
    -> normalise the genre -> fetch lyrics/cover -> write tags -> rename

Each step can fail without killing the run; whatever could not be completed is
recorded in the manifest, so the report explains what happened instead of
silently skipping it.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import genres as gn
from . import naming
from . import providers as pv
from . import tags as tg
from . import translit
from .config import Config
from .manifest import Entry
from .matching import pick, score
from .naming import fold
from .scripts import compose

SPOTIFY_ID_RE = re.compile(r"open\.spotify\.com/track/([A-Za-z0-9]+)")
MIN_COVER_BYTES = 8_000
COVER_RE = re.compile(rb"(\xff\xd8\xff|\x89PNG\r\n\x1a\n)")

# Covers are fetched once during planning and held in memory for the apply
# pass; the manifest records only the URL, because a 700 KB JPEG does not
# belong in JSON.
Covers = dict[str, tuple[bytes, int]]


# --------------------------------------------------------------------- helpers

def existing_spotify_id(path: Path) -> str:
    """A Spotify ID left in the file by a previous tagger, if there is one."""
    for key, value in tg.read(path).items():
        if key in ("comment", "spotify_id") or key.startswith("comment"):
            m = SPOTIFY_ID_RE.search(value or "")
            if m:
                return m.group(1)
    return ""


def fetch_cover(url: str) -> tuple[bytes, int] | None:
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": pv.UA})
        with urllib.request.urlopen(req, timeout=pv.TIMEOUT) as r:
            data = r.read(12_000_000)
    except Exception:
        return None
    if len(data) < MIN_COVER_BYTES or not COVER_RE.match(data):
        return None
    return data, len(data)


def _lang_of(data: dict) -> str:
    """Guess the region from the artist/album, for genre prefixing."""
    for field_ in ("album_artist", "artist", "album", "title"):
        comp = compose(data.get(field_, "") or "")
        if comp.hangul:
            return "ko"
        if comp.hiragana or comp.kanji or comp.katakana:
            return "ja"
    return ""


# --------------------------------------------------------------------- resolve

@dataclass
class Resolved:
    data: dict = field(default_factory=dict)
    source: str = ""
    confidence: float = 0.0
    latin_alias: str = ""
    notes: list = field(default_factory=list)


def resolve(path: Path, cfg: Config) -> Resolved:
    """Resolve metadata for one file. Never raises."""
    out = Resolved()
    parsed = naming.parse(path.name)
    artist, title = parsed["artist"], parsed["title"]

    # 1. an ID already in the file beats any search
    sid = existing_spotify_id(path)
    if sid:
        data = pv.spotify_get(sid)
        if data:
            out.data, out.source, out.confidence = data, "spotify-id", 1.0
            out.notes.append("resolved by Spotify ID already in the file")

    # 2. otherwise search, in provider priority order
    if not out.data:
        # A filename only implies which half is the artist and which is the
        # title. Files arrive in both layouts, so both readings are tried and
        # the scores decide - "Leo - Yuuri.mp3" must resolve to the song Leo,
        # not to an artist called Leo with a song called Yuuri.
        readings = [(artist, title, parsed["aliases"])]
        if artist and title and artist != title:
            readings.append((title, artist, []))
            out.notes.append(f"ambiguous layout, tried both readings: "
                             f"'{artist} | {title}' and '{title} | {artist}'")

        cands: dict[str, list[dict]] = {}
        seen: set[tuple] = set()
        for name, fn in pv.PROVIDERS:
            if name not in cfg.providers:
                continue
            for a, t, aliases in readings:
                try:
                    results = fn(a, t, limit=4)
                except Exception as exc:
                    out.notes.append(f"{name} failed: {exc!r}")
                    continue
                for c in results:
                    if not c.get("title"):
                        continue
                    key = (fold(c["title"]), fold(c["artist"]))
                    if key in seen:
                        continue
                    seen.add(key)
                    c["score"] = max(score(c, ra, rt, ra_alias)
                                     for ra, rt, ra_alias in readings)
                    cands.setdefault(name, []).append(c)
        best, source = pick(cands, artist, title, parsed["aliases"],
                            accept=cfg.accept, order=tuple(cfg.providers))
        if best:
            out.data, out.source, out.confidence = best, source, best["score"]
            if not out.notes or "ambiguous" not in out.notes[-1]:
                pass
        else:
            out.notes.append("no provider match above the confidence threshold")
            return out

    d = out.data

    # 3. the published Latin title, for katakana-only titles
    if cfg.translit_enabled and translit.needs_latin_alias(d.get("title", "")):
        out.latin_alias = pv.latin_alias_for_position(
            d.get("album_artist") or d.get("artist", ""), d.get("album", ""),
            d.get("year", ""), d.get("total_tracks", ""), d.get("track", ""))
        out.notes.append(
            f"katakana title; latin alias from Deezer tracklist: {out.latin_alias!r}"
            if out.latin_alias else
            "katakana title; no latin alias found, falling back to romaji")

    # 4. genre, normalised
    if d.get("genre"):
        d["genre_norm"] = gn.normalize(d["genre"], lang=cfg.genre_lang or _lang_of(d))
    elif cfg.default_genre:
        d["genre_norm"] = gn.normalize(cfg.default_genre, lang=cfg.genre_lang)
        out.notes.append(f"genre defaulted to {cfg.default_genre!r}")

    # 5. lyrics / composer
    if cfg.want_lyrics:
        try:
            d["lyrics"] = pv.lyrics(d.get("artist", ""), d.get("title", ""))
        except Exception as exc:
            out.notes.append(f"lyrics lookup failed: {exc!r}")
    if cfg.want_composer:
        try:
            d["composer"] = pv.musicbrainz_composer(d.get("artist", ""),
                                                    d.get("title", ""))
        except Exception as exc:
            out.notes.append(f"composer lookup failed: {exc!r}")
    return out


# --------------------------------------------------------------------- plan

VIDEO_EXTS = (".mp4",)


def scanned_exts(cfg: "Config") -> tuple[str, ...]:
    """Audio always, video only when asked for - most folders hold one or the
    other, and silently picking up a stray .mp4 would be surprising."""
    return tg.AUDIO_EXTS + (VIDEO_EXTS if cfg.include_video else ())


def plan(src: Path, cfg: Config) -> tuple[list[Entry], Covers]:
    """Resolve every supported file in `src`. Touches nothing."""
    src = Path(src)
    rows: list[Entry] = []
    covers: Covers = {}

    files = sorted(f for f in src.iterdir()
                   if f.is_file() and f.suffix.lower() in scanned_exts(cfg))
    for path in files:
        parsed = naming.parse(path.name)
        res = resolve(path, cfg)
        d = res.data

        title = d.get("title", "")
        if cfg.translit_enabled and title:
            title = translit.romanize_title(title, lang=cfg.translit,
                                            latin_alias=res.latin_alias)

        cover = fetch_cover(d.get("cover_url", "")) if cfg.want_cover else None
        if cover:
            covers[path.name] = cover

        ext = path.suffix.lstrip(".")
        entry = Entry(
            old_name=path.name, old_size=path.stat().st_size,
            parsed_artist=parsed["artist"], parsed_title=parsed["title"],
            parsed_index=parsed["index"],
            source=res.source, confidence=res.confidence,
            spotify_id=d.get("spotify_id", ""),
            title=d.get("title", ""), title_romanized=title,
            title_latin_alias=res.latin_alias,
            artist=d.get("artist", ""), album=d.get("album", ""),
            album_artist=d.get("album_artist", ""),
            genre=d.get("genre_norm", ""),
            date=d.get("date") or d.get("year", ""),
            track=d.get("track", ""), total_tracks=d.get("total_tracks", ""),
            lyrics=d.get("lyrics", ""), composer=d.get("composer", ""),
            cover_source=d.get("source", "") if cover else "",
            cover_bytes=cover[1] if cover else 0,
            comment=d.get("comment", ""), notes=list(res.notes),
        )
        entry.new_name = naming.format_name(
            entry.artist, naming.display_title(title, entry.artist),
            style=cfg.name_style, ext=ext)
        rows.append(entry)

    _dedupe(rows)
    return rows, covers


def _dedupe(rows: list[Entry]) -> None:
    """Two files resolving to the same name must not overwrite each other."""
    taken: set[str] = set()
    for r in rows:
        if not r.new_name:
            continue
        stem, ext = r.new_name.rsplit(".", 1)
        base, i, name = stem, 2, r.new_name
        while name in taken:
            name, i = f"{stem} ({i}).{ext}", i + 1
        r.new_name = name
        taken.add(name)


# --------------------------------------------------------------------- apply

def apply(src: Path, rows: list[Entry], cfg: Config, covers: Covers | None = None) -> tuple[int, int]:
    """Write tags and rename. Returns (applied, failed)."""
    src = Path(src)
    dest = cfg.dest or src
    if cfg.dry_run:
        return sum(1 for r in rows if r.title), 0

    covers = covers or {}
    tmpdir = Path(tempfile.mkdtemp(prefix="music-tag-"))
    done = fail = 0
    try:
        for r in rows:
            src_path = src / r.old_name
            if not src_path.exists():
                r.error = "source file disappeared"
                fail += 1
                continue
            if not r.title:
                r.error = "no metadata resolved"
                fail += 1
                continue
            staged = tmpdir / r.old_name
            try:
                shutil.copy2(src_path, staged)
                tags = tg.TagSet(
                    title=r.title_romanized or r.title, artist=r.artist,
                    album=r.album, album_artist=r.album_artist, genre=r.genre,
                    date=r.date, track=r.track, total_tracks=r.total_tracks,
                    disc="1", comment=r.comment,
                    grouping="Official M/V" if cfg.group_video else "",
                    composer=r.composer,
                    extra={"Spotify ID": r.spotify_id} if r.spotify_id else {},
                )
                cover = covers.get(r.old_name)
                tg.write(staged, tags, cover=cover[0] if cover else None,
                         lyrics=r.lyrics, workdir=tmpdir)
                r.new_size = staged.stat().st_size

                dest.mkdir(parents=True, exist_ok=True)
                staged.replace(dest / r.new_name)
                if dest == src and r.new_name != r.old_name:
                    (src / r.old_name).unlink(missing_ok=True)
                r.applied = True
                done += 1
            except Exception as exc:
                staged.unlink(missing_ok=True)
                r.error = repr(exc)
                fail += 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return done, fail

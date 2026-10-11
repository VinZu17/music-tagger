"""Metadata sources.

Every source answers the same question with the same shape so the caller does
not care where a field came from. Sources are tried in the order they appear
in PROVIDERS; the first one whose best candidate clears the confidence bar
wins, which is what keeps a cheap anonymous source from being outrun by a
better one that happens to be slower.

Search is by *artist + title*, but the album lookup works differently on
purpose: Deezer does not index Japanese album names, so an album is found by
its *shape* (artist + release year + track count) and its tracklist is used
positionally to recover international titles. That is how a title like
ビリミリオン, which Spotify keeps in Japanese, ends up tagged "Billimillion".
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

UA = "music-tagger/1.0 (https://github.com/VinZu17/music-tagger)"
TIMEOUT = 25


def _get(url: str, headers: dict | None = None) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


def fold(s: str) -> str:
    """Casefold, NFKC, drop punctuation but keep letters of every script.

    An [a-z0-9] filter here silently destroys Japanese titles, which is why
    the letters themselves are kept and only separators are removed.
    """
    return re.sub(r"[\s\-_'\.,!\?:;#/\\()\[\]{}\"'`~「」『』・]+", "",
                  unicodedata.normalize("NFKC", s or "").casefold())


def _cand(**kw) -> dict:
    base = {
        "source": "", "title": "", "artist": "", "album": "", "album_artist": "",
        "year": "", "date": "", "track": "", "total_tracks": "", "genre": "",
        "isrc": "", "label": "", "cover_url": "", "share_url": "",
        "spotify_id": "", "explicit": "",
    }
    base.update({k: v for k, v in kw.items() if v not in (None, "")})
    return base


# --------------------------------------------------------------------------- Spotify

_spotify = None


def _client():
    global _spotify
    if _spotify is None:
        from spotify_scraper import SpotifyClient
        _spotify = SpotifyClient()
        _spotify.__enter__()
    return _spotify


def spotify_get(track_id: str) -> dict | None:
    """Fetch one track by its Spotify ID. No API key, no account."""
    try:
        c = _client()
        t = c.get_track(track_id)
        a = c.get_album(t.album.uri) if getattr(t.album, "uri", None) else None
    except Exception:
        return None
    if a is None:
        return None
    imgs = [i for i in (a.images or []) if getattr(i, "url", None)]
    best = max(imgs, key=lambda i: getattr(i, "width", 0)) if imgs else None
    return _cand(
        source="spotify", spotify_id=track_id,
        title=t.name, artist=", ".join(x.name for x in t.artists),
        album=a.name, album_artist=", ".join(x.name for x in a.artists),
        year=str(a.release_date)[:4] if a.release_date else "",
        date=str(a.release_date)[:10] if a.release_date else "",
        track=str(t.track_number or ""),
        total_tracks=str(a.total_tracks or ""),
        label=a.label or "",
        cover_url=best.url if best else "",
        share_url=t.share_url or f"https://open.spotify.com/track/{track_id}",
        explicit="yes" if t.explicit else "",
    )


def spotify_search(artist: str, title: str, limit: int = 4) -> list[dict]:
    try:
        res = _client().search(f"{artist} {title}".strip(), types=("track",), limit=limit)
    except Exception:
        return []
    out, seen_albums = [], {}
    for t in getattr(res, "tracks", []) or []:
        alb = t.album
        cand = _cand(
            source="spotify", spotify_id=t.id,
            title=t.name, artist=", ".join(x.name for x in t.artists),
            album=getattr(alb, "name", "") or "",
            year=str(getattr(t, "release_date", "") or "")[:4],
            date=str(getattr(t, "release_date", "") or "")[:10],
            track=str(getattr(t, "track_number", "") or ""),
            share_url=t.share_url or f"https://open.spotify.com/track/{t.id}",
            explicit="yes" if t.explicit else "",
        )
        # search results carry an AlbumRef with no release date or track count,
        # and those are exactly what the katakana/latin-alias step needs
        uri = getattr(alb, "uri", None)
        if uri:
            if uri not in seen_albums:
                try:
                    seen_albums[uri] = _client().get_album(uri)
                except Exception:
                    seen_albums[uri] = None
            full = seen_albums[uri]
            if full:
                cand["album_artist"] = ", ".join(x.name for x in full.artists)
                cand["total_tracks"] = str(full.total_tracks or "")
                cand["year"] = str(full.release_date or "")[:4]
                cand["date"] = str(full.release_date or "")[:10]
                cand["label"] = full.label or ""
                imgs = [i for i in (full.images or []) if getattr(i, "url", None)]
                if imgs:
                    cand["cover_url"] = max(imgs, key=lambda i: getattr(i, "width", 0)).url
        out.append(cand)
    return out


# --------------------------------------------------------------------------- Deezer

def deezer_search(artist: str, title: str, limit: int = 6) -> list[dict]:
    q = urllib.parse.quote(f"{artist} {title}".strip())
    data = _get(f"https://api.deezer.com/search?q={q}&limit={limit}")
    out = []
    for t in (data or {}).get("data") or []:
        alb = t.get("album") or {}
        out.append(_cand(
            source="deezer", title=t.get("title"), artist=(t.get("artist") or {}).get("name"),
            album=alb.get("title"), isrc=t.get("isrc"),
            cover_url=alb.get("cover_xl") or alb.get("cover_big") or "",
            share_url=t.get("link"),
        ))
    return out


def deezer_album_by_shape(artist: str, *, year: str = "", tracks: str = "") -> dict | None:
    """Find an album on Deezer by artist + release year + track count.

    Deezer does not index Japanese album names, so matching on the name is
    not an option. Shape matching is stronger than it sounds: a year plus a
    track count narrows a whole discography down to one release.
    """
    want_tracks = int(tracks) if str(tracks).isdigit() else 0
    d = _get(f"https://api.deezer.com/search/album?limit=40&q={urllib.parse.quote(artist)}")
    for a in (d or {}).get("data") or []:
        det = _get(f"https://api.deezer.com/album/{a['id']}")
        if not det:
            continue
        got = len((det.get("tracks") or {}).get("data") or [])
        if want_tracks and got != want_tracks:
            continue
        if year and str(det.get("release_date") or "")[:4] != str(year):
            continue
        return det
    return None


def deezer_album_titles(album_id: int | str) -> list[str]:
    """The album's tracklist, in release order."""
    det = _get(f"https://api.deezer.com/album/{album_id}")
    return [t.get("title") for t in (det or {}).get("tracks", {}).get("data", [])
            if t.get("title")]


def latin_alias_for_position(artist: str, album: str, year: str,
                             total_tracks: str, position: str) -> str:
    """The published Latin title for track `position` of this album, or ''.

    Returns '' whenever anything is uncertain - an empty result just means the
    caller keeps the romanized title, which is always safe.
    """
    if not (str(position or "").isdigit() and int(position) > 0):
        return ""
    det = deezer_album_by_shape(artist, year=year, tracks=total_tracks)
    if not det:
        return ""
    titles = deezer_album_titles(det["id"])
    i = int(position) - 1
    if i >= len(titles):
        return ""
    return titles[i] or ""


# --------------------------------------------------------------------------- iTunes

def itunes_search(artist: str, title: str, limit: int = 4, countries=("JP", "US", "GB")) -> list[dict]:
    q = urllib.parse.quote(f"{artist} {title}".strip())
    for country in countries:
        data = _get(f"https://itunes.apple.com/search?term={q}&entity=song"
                    f"&limit={limit}&country={country}")
        out = []
        for t in (data or {}).get("results") or []:
            art = (t.get("artworkUrl100") or "").replace("100x100", "1200x1200")
            out.append(_cand(
                source="itunes", title=t.get("trackName"), artist=t.get("artistName"),
                album=t.get("collectionName"), year=str(t.get("releaseDate") or "")[:4],
                date=str(t.get("releaseDate") or "")[:10],
                track=str(t.get("trackNumber") or ""), genre=t.get("primaryGenreName"),
                cover_url=art, share_url=t.get("trackViewUrl"),
            ))
        if out:
            return out
    return []


# --------------------------------------------------------------------------- MusicBrainz

def musicbrainz_composer(artist: str, title: str) -> str:
    """Songwriter credit, which Spotify does not expose."""
    q = urllib.parse.quote(f'artist:"{artist}" AND recording:"{title}"')
    data = _get(f"https://musicbrainz.org/ws/2/recording?query={q}&fmt=json&limit=5",
                {"User-Agent": UA})
    want = fold(title)
    best, score = "", 0.0
    for r in (data or {}).get("recordings") or []:
        names = [a.get("name") for rel in r.get("relations") or []
                 if rel.get("type") in ("composer", "writer", "lyricist")
                 for a in rel.get("artist") or []]
        if not names:
            continue
        s = 1.0 if fold(r.get("title", "")) == want else 0.0
        if s > score:
            best, score = ", ".join(dict.fromkeys(names)), s
    return best


# --------------------------------------------------------------------------- Lyrics

def lyrics_lrclib(artist: str, title: str) -> str:
    q = urllib.parse.urlencode({"artist_name": artist, "track_name": title})
    data = _get(f"https://lrclib.net/api/search?{q}", {"User-Agent": UA})
    if isinstance(data, list) and data:
        want = fold(title)
        for hit in data:
            if want and fold(hit.get("trackName") or "") == want:
                return hit.get("plainLyrics") or ""
    q = urllib.parse.urlencode({"q": f"{artist} {title}"})
    data = _get(f"https://lrclib.net/api/search?{q}", {"User-Agent": UA})
    if not isinstance(data, list):
        return ""
    want = fold(title)
    for hit in data:
        name = fold(hit.get("trackName") or "")
        if name and (name == want or (len(want) > 3 and (want in name or name in want))):
            return hit.get("plainLyrics") or ""
    return ""


def lyrics_ovh(artist: str, title: str) -> str:
    url = ("https://api.lyrics.ovh/v1/"
           + urllib.parse.quote((artist or "").strip(), safe="")
           + "/" + urllib.parse.quote((title or "").strip(), safe=""))
    data = _get(url)
    return (data or {}).get("lyrics", "") if isinstance(data, dict) else ""


def lyrics(artist: str, title: str) -> str:
    """lrclib first (better coverage), lyrics.ovh as fallback."""
    primary = re.split(r",| feat", artist or "", maxsplit=1)[0].strip()
    for fn in (lyrics_lrclib, lyrics_ovh):
        text = fn(primary, title)
        if len(text.strip()) > 40:
            return text.strip()
    return ""


# --------------------------------------------------------------------------- registry

PROVIDERS = (("spotify", spotify_search), ("deezer", deezer_search),
             ("itunes", itunes_search))

PROVIDER_NAMES = tuple(n for n, _ in PROVIDERS)

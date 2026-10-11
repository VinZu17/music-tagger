"""Writing tags, for every format we support.

Two writers, because the containers are genuinely different:

* audio (MP3/FLAC/M4A/OGG/Opus/WAV) - mutagen, in place, never re-encodes
* video (MP4) - the tag data lives in a moov atom that mutagen cannot build,
  so ffmpeg re-muxes with `-c copy`, which copies the video and audio packets
  byte for byte and only rewrites the container

Both writers take the same `TagSet`, so the rest of the code does not know or
care which one is in use.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


@dataclass
class TagSet:
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    genre: str = ""
    date: str = ""
    track: str = ""
    total_tracks: str = ""
    disc: str = "1"
    comment: str = ""
    grouping: str = ""
    composer: str = ""
    label: str = ""
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in
             ("title", "artist", "album", "album_artist", "genre", "date", "track",
              "total_tracks", "disc", "comment", "grouping", "composer", "label")}
        d.update(self.extra)
        return {k: v for k, v in d.items() if v}


def _track_pair(t: str, total: str) -> str:
    t = str(t or "").strip()
    total = str(total or "").strip()
    if not t:
        return ""
    return f"{t}/{total}" if total else t


# --------------------------------------------------------------------- audio

AUDIO_EXTS = (".mp3", ".flac", ".m4a", ".m4b", ".ogg", ".opus", ".wav", ".ape", ".wma")


def write_audio(path, tags: TagSet, *, cover: bytes | None = None,
                lyrics: str = "") -> None:
    """Write tags in place with mutagen. The audio stream is untouched."""
    import mutagen

    audio = mutagen.File(str(path), easy=False)
    if audio is None:
        raise RuntimeError(f"mutagen cannot read {path}")
    track = _track_pair(tags.track, tags.total_tracks)
    values = {
        "title": tags.title, "artist": tags.artist, "album": tags.album,
        "albumartist": tags.album_artist, "genre": tags.genre, "date": tags.date,
        "tracknumber": track, "discnumber": tags.disc,
        "composer": tags.composer, "comment": tags.comment,
        "grouping": tags.grouping, "label": tags.label,
    }
    if audio.__class__.__name__ == "ID3" or type(audio).__name__ == "MP3":
        _write_id3(path, tags, track, cover, lyrics)
        return
    if type(audio).__name__ in ("MP4", "M4A"):
        _write_mp4_audio(path, tags, track, cover, lyrics)
        return
    # FLAC / OGG / Opus / WAV: Vorbis comments
    for k, v in values.items():
        if v:
            audio[k] = [v]
        elif k in audio:
            del audio[k]
    if cover:
        from mutagen.flac import Picture

        pic = Picture()
        pic.data = cover
        pic.type = 3
        pic.mime = "image/jpeg" if cover[:3] == b"\xff\xd8\xff" else "image/png"
        pic.desc = "Cover"
        audio.clear_pictures()
        audio.add_picture(pic)
    if lyrics:
        audio["lyrics"] = [lyrics]
    audio.save()


def _write_id3(path, tags: TagSet, track: str, cover: bytes | None, lyrics: str) -> None:
    from mutagen.id3 import (APIC, COMM, ID3, TALB, TCOM, TCON, TDRC, TIT2, TPE1,
                             TPE2, TPOS, TPUB, TRCK, TXXX, USLT)

    try:
        id3 = ID3(str(path))
    except Exception:
        id3 = ID3()
    id3.delall("APIC")
    if cover:
        id3.add(APIC(encoding=3, mime=_cover_mime(cover), type=3, desc="Cover", data=cover))
    id3.delall("TIT2"); id3.add(TIT2(encoding=3, text=tags.title))
    id3.delall("TPE1"); id3.add(TPE1(encoding=3, text=tags.artist))
    id3.delall("TPE2"); id3.add(TPE2(encoding=3, text=tags.album_artist))
    id3.delall("TALB"); id3.add(TALB(encoding=3, text=tags.album))
    id3.delall("TCON"); id3.add(TCON(encoding=3, text=tags.genre))
    id3.delall("TDRC"); id3.add(TDRC(encoding=3, text=tags.date))
    id3.delall("TRCK"); id3.add(TRCK(encoding=3, text=track))
    id3.delall("TPOS"); id3.add(TPOS(encoding=3, text=tags.disc))
    if tags.composer:
        id3.delall("TCOM"); id3.add(TCOM(encoding=3, text=tags.composer))
    if tags.label:
        id3.delall("TPUB"); id3.add(TPUB(encoding=3, text=tags.label))
    if tags.grouping:
        id3.delall("TIT1"); id3.add(TIT1(encoding=3, text=tags.grouping))
    id3.delall("USLT")
    if lyrics:
        id3.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))
    id3.delall("COMM")
    if tags.comment:
        id3.add(COMM(encoding=3, lang="eng", desc="", text=tags.comment))
    for k, v in (tags.extra or {}).items():
        id3.delall(f"TXXX:{k}")
        id3.add(TXXX(encoding=3, desc=k, text=str(v)))
    # ID3v1 is latin-1 and truncates at 30 characters; writing it would mangle
    # non-Latin titles for any player that prefers it.
    id3.save(str(path), v2_version=4, v1=0, padding=lambda _t: 1024)


def _write_mp4_audio(path, tags: TagSet, track: str, cover: bytes | None, lyrics: str) -> None:
    """M4A/MP4 audio via mutagen's MP4 class (no re-mux needed for audio-only)."""
    from mutagen.mp4 import MP4, MP4Cover

    audio = MP4(str(path))
    m = {
        "\xa9nam": tags.title, "\xa9ART": tags.artist, "\xa9alb": tags.album,
        "aART": tags.album_artist, "\xa9gen": tags.genre, "\xa9day": tags.date,
        "\xa9cmt": tags.comment, "\xa9grp": tags.grouping, "\xa9wrt": tags.composer,
    }
    for k, v in m.items():
        audio[k] = [v] if v else []
    if track:
        try:
            n, total = (track.split("/") + [""])[:2]
            audio["trkn"] = [(int(n), int(total or 0))]
        except ValueError:
            pass
    if tags.disc:
        try:
            audio["disk"] = [(int(tags.disc), 0)]
        except ValueError:
            pass
    audio["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)] if cover else []
    audio["\xa9lyr"] = [lyrics] if lyrics else []
    audio.save()


def _cover_mime(cover: bytes) -> str:
    return "image/png" if cover[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


# --------------------------------------------------------------------- video

def write_video(path, tags: TagSet, *, cover: bytes | None = None,
                lyrics: str = "", workdir=None) -> None:
    """Re-mux an MP4/MV with new tags. Streams are copied, never re-encoded."""
    from pathlib import Path

    path = Path(path)
    out = path.with_name(f".tag-{path.name}")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path)]
    cover_file = None
    if cover:
        cover_file = (workdir or path.parent) / f".cover-{path.stem}.jpg"
        cover_file.write_bytes(cover)
        cmd += ["-i", str(cover_file)]
    cmd += ["-map", "0", "-map_metadata", "-1", "-map_chapters", "-1"]
    if cover:
        cmd += ["-map", "1"]
    cmd += ["-c", "copy", "-movflags", "+faststart"]
    if cover:
        cmd += ["-disposition:v:1", "attached_pic",
                "-metadata:s:v:1", "title=Album cover",
                "-metadata:s:v:1", "comment=Cover (front)"]
    values = {
        "title": tags.title, "artist": tags.artist, "album_artist": tags.album_artist,
        "album": tags.album, "date": tags.date, "track": tags.track, "disc": tags.disc,
        "genre": tags.genre, "grouping": tags.grouping, "comment": tags.comment,
    }
    if lyrics:
        values["lyrics"] = lyrics
    for k, v in values.items():
        if v:
            cmd += ["-metadata", f"{k}={v}"]
    cmd += ["-f", "mp4", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        out.replace(path)
    finally:
        if cover_file and cover_file.exists():
            cover_file.unlink(missing_ok=True)
        out.unlink(missing_ok=True)


def write(path, tags: TagSet, *, cover: bytes | None = None, lyrics: str = "",
          workdir=None) -> None:
    """Dispatch to the right writer based on the file extension."""
    from pathlib import Path

    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".mp4":
        write_video(path, tags, cover=cover, lyrics=lyrics, workdir=workdir)
    elif ext in AUDIO_EXTS:
        write_audio(path, tags, cover=cover, lyrics=lyrics)
    else:
        raise ValueError(f"unsupported extension {ext!r} for {path}")


def read(path) -> dict:
    """Read tags back, normalised across formats."""
    from pathlib import Path

    path = Path(path)
    if path.suffix.lower() == ".mp3":
        return _read_id3(path)
    import mutagen

    audio = mutagen.File(str(path), easy=False)
    if audio is None:
        return {}
    if type(audio).__name__ in ("MP4", "M4A"):
        keys = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb",
                "album_artist": "aART", "genre": "\xa9gen", "date": "\xa9day",
                "comment": "\xa9cmt", "grouping": "\xa9grp", "lyrics": "\xa9lyr"}
        out = {k: (audio.get(v) or [""])[0] for k, v in keys.items()}
        out["cover"] = len(audio.get("covr") or [])
        return {k: v for k, v in out.items() if v}
    out = {k: (audio.get(k) or [""])[0] for k in
           ("title", "artist", "album", "albumartist", "genre", "date", "comment",
            "grouping", "lyrics")}
    out["album_artist"] = out.pop("albumartist", "")
    return {k: v for k, v in out.items() if v}


def _read_id3(path) -> dict:
    from mutagen.id3 import ID3

    try:
        id3 = ID3(str(path))
    except Exception:
        return {}
    get = lambda k: (str(id3[k]) if k in id3 else "")
    comment = ""
    for k, v in id3.items():
        if k.startswith("COMM"):
            txt = getattr(v, "text", None)
            comment = (txt[0] if isinstance(txt, list) and txt else str(txt)) or ""
            break
    out = {
        "title": get("TIT2"), "artist": get("TPE1"), "album": get("TALB"),
        "album_artist": get("TPE2"), "genre": get("TCON"), "date": get("TDRC"),
        "track": get("TRCK"), "disc": get("TPOS"),
        "comment": comment,
        "grouping": get("TIT1"), "composer": get("TCOM"), "label": get("TPUB"),
    }
    for k, v in id3.items():
        if k.startswith("USLT"):
            out["lyrics"] = str(v.text)
        if k.startswith("APIC"):
            out["cover"] = len(v.data)
    return {k: v for k, v in out.items() if v}

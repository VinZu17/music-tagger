"""Video (MP4) path.

A music video carries the same metadata as a song, and the tags live in a moov
atom mutagen cannot build, so ffmpeg re-muxes. The promise that matters here is
that `-c copy` leaves the video and audio packets byte-identical - if that ever
regresses, music videos get re-encoded and the file grows for no reason.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from music_tagger import core
from music_tagger.config import Config
from music_tagger.tags import TagSet, write

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg needed")


def _make_mp4(path: Path):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True)
    return path


def _payload_md5(path, sel):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
                        "-map", sel, "-f", "md5", "-"], capture_output=True, text=True)
    return r.stdout.strip()


def _tags(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags",
                        "-of", "default=nw=1", str(path)],
                       capture_output=True, text=True).stdout
    out = {}
    for line in r.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")   # values may themselves contain '='
        key = key.strip()
        out[key[4:] if key.startswith("TAG:") else key] = value
    return out


def _real_cover(tmp_path: Path) -> bytes:
    """A genuinely decodable JPEG - ffmpeg rejects a byte-stuffed fake."""
    out = tmp_path / "cover.jpg"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=red:s=600x600",
                    "-frames:v", "1", str(out)], check=True, capture_output=True)
    return out.read_bytes()


def test_video_tags_and_cover(tmp_path):
    path = _make_mp4(tmp_path / "001 - BLACKPINK - Pink Venom.mp4")
    before_v, before_a = _payload_md5(path, "0:v:0"), _payload_md5(path, "0:a:0")

    write(path, TagSet(title="Pink Venom", artist="BLACKPINK", album="BORN PINK",
                       genre="K-Pop", date="2022", track="2", grouping="Official M/V"),
          cover=_real_cover(tmp_path), lyrics="kick in the door")

    got = _tags(path)
    assert got["title"] == "Pink Venom"
    assert got["artist"] == "BLACKPINK"
    assert got["album"] == "BORN PINK"
    assert got["grouping"] == "Official M/V"
    assert got["track"] == "2"
    assert got["lyrics"].startswith("kick in the door")

    assert _payload_md5(path, "0:v:0") == before_v, "video payload changed"
    assert _payload_md5(path, "0:a:0") == before_a, "audio payload changed"


def test_cover_atom_present(tmp_path):
    path = _make_mp4(tmp_path / "a.mp4")
    write(path, TagSet(title="T", artist="A"), cover=_real_cover(tmp_path))
    assert b"covr" in path.read_bytes()[:4_000_000]


def test_video_not_scanned_by_default(tmp_path):
    _make_mp4(tmp_path / "a.mp4")
    cfg = Config(src=tmp_path, include_video=False)
    rows, _ = core.plan(tmp_path, cfg)
    assert rows == []


def test_video_scanned_when_requested(tmp_path):
    _make_mp4(tmp_path / "001 - BLACKPINK - Pink Venom.mp4")
    cfg = Config(src=tmp_path, include_video=True)
    rows, _ = core.plan(tmp_path, cfg)   # no providers stubbed -> no match, but it is seen
    assert len(rows) == 1
    assert rows[0].old_name.endswith(".mp4")


def test_scanned_exts(tmp_path):
    from music_tagger.core import scanned_exts
    assert ".mp4" not in scanned_exts(Config(src=tmp_path))
    assert ".mp4" in scanned_exts(Config(src=tmp_path, include_video=True))
    assert ".mp3" in scanned_exts(Config(src=tmp_path))
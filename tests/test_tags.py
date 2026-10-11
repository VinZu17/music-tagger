"""Tag writing, exercised on real files generated with ffmpeg.

Each test builds a tiny media file, writes tags through music_tagger.tags,
reads them back, and checks the audio payload survived untouched - because
"tags changed but the music did not" is the whole promise of this tool.
"""

import shutil
import subprocess

import pytest

from music_tagger.tags import TagSet, read, write

pytestmark = pytest.mark.usefixtures("ffmpeg")

FFMPEG = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")

GEN_ARGS = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:a", "libmp3lame", "-q:a", "9"]

FORMATS = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "9"],
    "flac": ["-c:a", "flac"],
    "m4a": ["-c:a", "aac", "-b:a", "32k"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "0"],
    "opus": ["-c:a", "libopus", "-b:a", "24k"],
}


@pytest.fixture(scope="module")
def ffmpeg():
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    return True


def _payload_md5(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
                        "-map", "0:a", "-f", "md5", "-"], capture_output=True, text=True)
    out = r.stdout.strip()
    return out.split("MD5=")[-1] if "MD5=" in out else None


def _make(tmp_path, ext):
    path = tmp_path / f"src.{ext}"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    *FORMATS[ext], str(path)], check=True, capture_output=True)
    return path


TAGS = TagSet(title="Birimirion", artist="Yuuri", album="Ni", album_artist="Yuuri",
              genre="J-Rock", date="2023-03-29", track="3", total_tracks="14",
              disc="1", comment="metadata: spotify | https://open.spotify.com/track/xyz")


@pytest.mark.parametrize("ext", list(FORMATS))
def test_roundtrip_all_formats(tmp_path, ext):
    path = _make(tmp_path, ext)
    before = _payload_md5(path)

    write(path, TAGS, lyrics="line one\nline two")
    got = read(path)

    assert got["title"] == "Birimirion"
    assert got["artist"] == "Yuuri"
    assert got["album"] == "Ni"
    assert got["genre"] == "J-Rock"
    assert "2023" in got["date"]
    assert got["lyrics"].startswith("line one")
    if ext != "opus":
        assert got["album_artist"] == "Yuuri"
    assert _payload_md5(path) == before, f"{ext}: audio payload changed"


def test_cover_art_survives_roundtrip(tmp_path):
    cover = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
             b"\xff\xd9")
    path = _make(tmp_path, "mp3")
    write(path, TAGS, cover=cover)
    assert read(path)["cover"] == len(cover)


def test_comment_format_is_preserved(tmp_path):
    path = _make(tmp_path, "mp3")
    write(path, TAGS)
    assert read(path)["comment"] == TAGS.comment


def test_unsupported_extension_raises(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("not music")
    with pytest.raises(ValueError):
        write(p, TAGS)


def test_vorbis_cover(tmp_path):
    pytest.importorskip("mutagen.flac")
    cover = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
             b"\xff\xd9")
    path = _make(tmp_path, "flac")
    write(path, TAGS, cover=cover)
    import mutagen
    f = mutagen.File(str(path))
    assert len(f.pictures) == 1
    assert f.pictures[0].type == 3

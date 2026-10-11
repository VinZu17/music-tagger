"""End-to-end tests for the pipeline, against a local fake provider.

These run the real code path - parse, resolve, romanize, tag, rename - but the
network is replaced by a stub, so the tests are deterministic and fast.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from music_tagger import core
from music_tagger.config import Config
from music_tagger.tags import read

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg needed")


# ----------------------------------------------------------------- fixtures

@pytest.fixture
def fake_providers(monkeypatch):
    """Replace every network call with data for two fixed songs.

    The search functions are what the pipeline actually calls (files in the
    fixture carry no Spotify ID yet), so PROVIDERS itself is patched rather
    than the individual helpers.
    """

    def spotify_get(tid):
        if tid == "ID_KATAKANA":
            return {"source": "spotify", "spotify_id": tid,
                    "title": "ビリミリオン", "artist": "Yuuri", "album": "弐",
                    "album_artist": "Yuuri", "year": "2023", "date": "2023-03-29",
                    "track": "1", "total_tracks": "14", "genre": "",
                    "cover_url": "", "share_url": f"https://open.spotify.com/track/{tid}"}
        if tid == "ID_KANJI":
            return {"source": "spotify", "spotify_id": tid,
                    "title": "恋人じゃなくなった日", "artist": "Yuuri", "album": "弐",
                    "album_artist": "Yuuri", "year": "2023", "date": "2023-03-29",
                    "track": "3", "total_tracks": "14", "genre": "ロック",
                    "cover_url": "", "share_url": f"https://open.spotify.com/track/{tid}"}
        return None

    def spotify_search(artist, title, limit=4):
        # a real catalogue holds both the native and the international title,
        # which is how a search for the romanized name finds the record
        known = [spotify_get("ID_KATAKANA"), spotify_get("ID_KANJI")]
        en = dict(spotify_get("ID_KATAKANA") or {}, title="Billimillion",
                  spotify_id="ID_ENGLISH")
        known.append(en)
        out = []
        for d in known:
            if d and (not title or d["title"] == title):
                c = dict(d)
                c["score"] = 1.0
                out.append(c)
        return out

    def latin_alias(artist, album, year, total, position):
        return {"1": "Billimillion", "3": ""}.get(str(position), "")

    monkeypatch.setattr(core.pv, "PROVIDERS",
                        (("spotify", spotify_search),
                         ("deezer", lambda a, t, limit=6: []),
                         ("itunes", lambda a, t, limit=4, countries=None: [])))
    monkeypatch.setattr(core.pv, "spotify_get", spotify_get)
    monkeypatch.setattr(core.pv, "latin_alias_for_position", latin_alias)
    monkeypatch.setattr(core.pv, "lyrics", lambda a, t: "la la la\n" * 8)
    monkeypatch.setattr(core.pv, "musicbrainz_composer", lambda a, t: "")
    return fake_providers


@pytest.fixture
def mp3_file(tmp_path):
    path = tmp_path / "Yuuri - ビリミリオン.mp3"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:a", "libmp3lame", "-q:a", "9", str(path)],
                   check=True, capture_output=True)
    return path


def _cfg(tmp_path, **kw):
    kw.setdefault("translit", "ja")
    kw.setdefault("genre_lang", "ja")
    return Config(src=tmp_path, **kw)


# --------------------------------------------------------------------- tests

def test_katakana_title_takes_published_english(mp3_file, fake_providers, tmp_path):
    rows, covers = core.plan(tmp_path, _cfg(tmp_path))
    assert len(rows) == 1
    r = rows[0]
    assert r.title_latin_alias == "Billimillion"
    assert r.title_romanized == "Billimillion"
    assert r.new_name == "Yuuri - Billimillion.mp3"


def test_kanji_title_is_romanized_not_replaced(mp3_file, fake_providers, tmp_path):
    mp3_file.rename(tmp_path / "Yuuri - 恋人じゃなくなった日.mp3")
    rows, _ = core.plan(tmp_path, _cfg(tmp_path))
    r = rows[0]
    assert r.title_romanized == "Koibito janakunatta nichi"
    assert r.genre == "J-Rock"


def test_no_translit_keeps_original_title(mp3_file, fake_providers, tmp_path):
    rows, _ = core.plan(tmp_path, _cfg(tmp_path, translit=""))
    assert rows[0].title_romanized == "ビリミリオン"
    assert rows[0].new_name == "Yuuri - ビリミリオン.mp3"


def test_title_artist_naming_style(mp3_file, fake_providers, tmp_path):
    rows, _ = core.plan(tmp_path, _cfg(tmp_path, name_style="title-artist"))
    assert rows[0].new_name == "Billimillion - Yuuri.mp3"


def test_dry_run_changes_nothing(mp3_file, fake_providers, tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    rows, covers = core.plan(tmp_path, _cfg(tmp_path))
    done, fail = core.apply(tmp_path, rows, _cfg(tmp_path, dry_run=True), covers)
    assert (done, fail) == (1, 0)
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert all(not r.applied for r in rows)


def test_apply_tags_and_renames(mp3_file, fake_providers, tmp_path):
    rows, covers = core.plan(tmp_path, _cfg(tmp_path))
    done, fail = core.apply(tmp_path, rows, _cfg(tmp_path), covers)
    assert (done, fail) == (1, 0)

    new = tmp_path / "Yuuri - Billimillion.mp3"
    assert new.exists()
    assert not (tmp_path / "Yuuri - ビリミリオン.mp3").exists()

    tags = read(new)
    assert tags["title"] == "Billimillion"
    assert tags["artist"] == "Yuuri"
    assert tags["album"] == "弐"
    assert tags["lyrics"].startswith("la la la")


def test_duplicate_names_get_numbered(mp3_file, fake_providers, tmp_path):
    """Two identical files must not overwrite each other."""
    second = tmp_path / "Yuuri - ビリミリオン (2).mp3"
    shutil.copy2(mp3_file, second)
    rows, _ = core.plan(tmp_path, _cfg(tmp_path))
    assert len({r.new_name for r in rows}) == 2
    assert any(r.new_name.endswith("(2).mp3") for r in rows)


def test_unresolved_file_is_reported_not_silent(tmp_path, fake_providers, monkeypatch):
    (tmp_path / "Unknown Artist - Unknown Song.mp3").write_bytes(b"\x00" * 64)
    monkeypatch.setattr(core.pv, "spotify_get", lambda tid: None)
    monkeypatch.setattr(core.pv, "spotify_search", lambda a, t, limit=4: [])
    monkeypatch.setattr(core.pv, "deezer_search", lambda a, t, limit=6: [])
    monkeypatch.setattr(core.pv, "itunes_search", lambda a, t, limit=4, countries=None: [])
    rows, _ = core.plan(tmp_path, _cfg(tmp_path))
    assert rows[0].title == ""
    assert any("no provider match" in n for n in rows[0].notes)


def test_manifest_roundtrip(mp3_file, fake_providers, tmp_path):
    from music_tagger.manifest import load, save
    rows, _ = core.plan(tmp_path, _cfg(tmp_path))
    path = tmp_path / "m.json"
    save(rows, path)
    loaded = load(path)
    assert loaded[0].title_romanized == "Billimillion"
    assert loaded[0].old_name == rows[0].old_name


def test_title_artist_layout_file_resolves(mp3_file, fake_providers, tmp_path):
    """'Title - Artist.mp3' must not be read as artist=Title.

    Files arrive in both layouts, so both readings are tried and the score
    decides. This is the regression test for exactly that.
    """
    mp3_file.rename(tmp_path / "Billimillion - Yuuri.mp3")
    rows, _ = core.plan(tmp_path, _cfg(tmp_path))
    r = rows[0]
    assert r.title_romanized == "Billimillion"
    assert r.artist == "Yuuri"
    assert r.confidence >= 0.72
    assert r.new_name == "Yuuri - Billimillion.mp3"

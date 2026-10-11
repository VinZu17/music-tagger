# music-tagger

Tag music files with metadata from the web, then rename them.

```bash
music-tagger "/mnt/music/Japanese" --translit ja --genre-lang ja
```

Spotify, Deezer, iTunes and MusicBrainz are all consulted; lyrics come from
lrclib. Audio is tagged with mutagen and never re-encoded, so the music itself
does not change - only the tags and the filename.

## What it does

```
$ music-tagger ./music --translit ja --genre-lang ja --dry-run
  #  conf  src           cov    title                           artist          -> new name
  1  1.00  spotify-id    -      Billimillion                    Yuuri           Yuuri - Billimillion.mp3
  2  1.00  spotify-id    -      Koibito janakunatta nichi       Yuuri           Yuuri - Koibito janakunatta nichi.mp3

applied 0, failed 0, total 2
manifest -> manifest.json
```

Drop `--dry-run` to actually write.

### Formats

| | audio | video |
|---|---|---|
| read + tag | MP3, FLAC, M4A, OGG, Opus, WAV, APE, WMA | MP4 |
| tag writer | mutagen, in place | ffmpeg `-c copy` (streams untouched) |

### Sources

| source | gives | needs |
|---|---|---|
| Spotify | track, album, year, track no. | nothing (anonymous token) |
| Deezer | **international titles**, album shape | nothing |
| iTunes | genre, 1200px cover | nothing |
| MusicBrainz | composer | nothing |
| lrclib | lyrics | nothing |

## Non-Latin titles

A title is not romanized by guessing at it. The script it is written in
decides the path:

| title is written in | what happens | why |
|---|---|---|
| **katakana** | the published English title is used | katakana is the script Japan borrows foreign words with; レオン romanizes to "reon" but the song is called **Leo** |
| **kanji / hiragana** | romanized locally (pykakasi) | native Japanese content, so a transcription is what is wanted |
| **Latin already** | left alone | nothing to do |

The English title comes from the *same album's* tracklist on Deezer, matched by
track position - not by text similarity. Deezer does not index Japanese album
names, so the album is found by its shape (artist + release year + track count)
and its tracklist read in order:

```
album 弐 (Spotify, 14 tracks, 2023)  ==  album "Ni" (Deezer, 14 tracks, 2023)
     track 1  ビリミリオン              ->  'Billimillion'
     track 3  恋人じゃなくなった日       ->  'The day we become eternal love,not lovers'
```

Positional matching means there is no fuzzy step to get wrong. It also means
`壱` cannot be mistaken for an unrelated song, which is exactly what happens
when you search for one instead.

Korean titles use the Revised Romanization (`korean-romanizer`).

## Filename layouts

```bash
music-tagger ./music                          # Artist - Title.mp3   (default)
music-tagger ./music --name-style title-artist  # Title - Artist.mp3
```

## Safety

* `--dry-run` plans and reports without touching anything
* `--backup DIR` copies the originals away first
* the **manifest** records the old and new name of every file, so a run can be
  reversed per file
* two files that resolve to the same name get numbered rather than overwriting
* a match below the confidence threshold is reported, never applied silently

## Install

```bash
pip install music-tagger            # audio tagging only
pip install "music-tagger[ja]"      # + Japanese romanization
pip install "music-tagger[ja,ko]"   # + Korean romanization
```

ffmpeg is only needed for MP4/MV files.

## CLI

```
music-tagger [source] [-o DEST] [-b BACKUP] [-m MANIFEST]

  --name-style {artist-title,title-artist}
  --translit {,ja,ko}          romanize non-Latin titles
  --genre-lang {,ja,ko,zh}     region prefix for genres
  --default-genre STR          when no provider supplies one
  --providers LIST             priority order (default spotify,deezer,itunes)
  --accept FLOAT               match confidence threshold (default 0.72)
  --no-lyrics / --no-cover / --no-composer
  --group-video                grouping='Official M/V' on video files
  -n, --dry-run                plan only
  -v, --verbose                show per-file reasoning
```

## Development

```bash
pip install -e ".[ja,ko,dev]"
pytest
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).

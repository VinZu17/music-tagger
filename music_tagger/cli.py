"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, core, manifest
from .config import Config
from .naming import STYLES


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="music-tagger",
        description="Tag music files with metadata from Spotify, Deezer, iTunes, "
                    "MusicBrainz and lrclib, then rename them.",
    )
    p.add_argument("--version", action="version", version=f"music-tagger {__version__}")

    p.add_argument("source", nargs="?", default=".",
                   help="folder of music files to process")
    p.add_argument("-o", "--dest", help="move tagged files here (default: in place)")
    p.add_argument("-b", "--backup", help="copy originals here before touching anything")
    p.add_argument("-m", "--manifest", default="manifest.json",
                   help="where to write the run manifest (default: ./manifest.json)")

    p.add_argument("--name-style", choices=STYLES, default="artist-title",
                   help="filename layout (default: artist-title)")
    p.add_argument("--translit", choices=("", "ja", "ko"), default="",
                   help="romanize non-Latin titles. 'ja' uses the published English "
                        "title for katakana and romaji for kanji/hiragana")
    p.add_argument("--genre-lang", choices=("", "ja", "ko", "zh"), default="",
                   help="region prefix for genres (ロック -> J-Rock with 'ja')")
    p.add_argument("--default-genre", default="",
                   help="genre to use when no provider supplies one")
    p.add_argument("--providers", default="spotify,deezer,itunes",
                   help="comma-separated provider priority (default: spotify,deezer,itunes)")
    p.add_argument("--accept", type=float, default=0.72,
                   help="confidence threshold for accepting a match (default: 0.72)")
    p.add_argument("--no-lyrics", action="store_true", help="skip lyrics")
    p.add_argument("--no-cover", action="store_true", help="skip cover art")
    p.add_argument("--no-composer", action="store_true", help="skip composer lookup")
    p.add_argument("--group-video", action="store_true",
                   help="set grouping='Official M/V' on video files")
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="plan and report, change nothing")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def cfg_from(args) -> Config:
    return Config(
        src=args.source, dest=args.dest, backup=args.backup,
        name_style=args.name_style, translit=args.translit,
        genre_lang=args.genre_lang, default_genre=args.default_genre,
        providers=tuple(x.strip() for x in args.providers.split(",") if x.strip()),
        accept=args.accept,
        want_lyrics=not args.no_lyrics, want_cover=not args.no_cover,
        want_composer=not args.no_composer,
        group_video=args.group_video, dry_run=args.dry_run, verbose=args.verbose,
    )


def _report(rows, done, fail, verbose):
    print(f"{'#':>3}  {'conf':>5}  {'src':<11} {'cov':<6} {'title':<30} {'artist':<20} -> new name")
    for n, r in enumerate(rows, 1):
        cov = f"{r.cover_bytes}B" if r.cover_bytes else "-"
        title = r.title_romanized or r.title
        print(f"{n:>3}  {r.confidence:.2f}  {r.source or 'no-match':<11} {cov:<6} "
              f"{title[:29]:<30} {r.artist[:19]:<20} {r.new_name or "-"}")
        if verbose:
            for note in r.notes:
                print(f"{'':>6}- {note}")
            if r.error:
                print(f"{'':>6}! {r.error}")
    print(f"\napplied {done}, failed {fail}, total {len(rows)}")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = cfg_from(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    src = Path(cfg.src)
    if not src.is_dir():
        print(f"error: {src} is not a directory", file=sys.stderr)
        return 2

    if cfg.backup:
        import shutil
        cfg.backup.mkdir(parents=True, exist_ok=True)
        print(f"backing up {src} -> {cfg.backup}")
        shutil.copytree(src, cfg.backup, dirs_exist_ok=True)

    print(f"planning {src} ...")
    rows, covers = core.plan(src, cfg)
    done, fail = core.apply(src, rows, cfg, covers)
    _report(rows, done, fail, cfg.verbose)

    manifest.save(rows, Path(args.manifest))
    print(f"manifest -> {args.manifest}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""Runtime configuration, all of it overridable from the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .naming import STYLES


@dataclass
class Config:
    """Everything a run needs that is not a per-file decision."""

    src: Path = Path(".")
    dest: Path | None = None          # None = edit in place
    backup: Path | None = None

    name_style: str = "artist-title"
    translit: str = ""                # "", "ja", "ko" - empty = never romanize

    genre_lang: str = ""              # "", "ja", "ko", "zh", ...
    default_genre: str = ""
    group_video: bool = False         # tag M/V files with grouping="Official M/V"

    providers: tuple[str, ...] = ("spotify", "deezer", "itunes")
    accept: float = 0.72
    want_lyrics: bool = True
    want_cover: bool = True
    want_composer: bool = True

    include_video: bool = False       # off by default; audio folders are the norm
    dry_run: bool = False
    verbose: bool = False

    def __post_init__(self):
        if self.name_style not in STYLES:
            raise ValueError(f"name_style must be one of {STYLES}, got {self.name_style!r}")
        self.src = Path(self.src).expanduser().resolve()
        if self.dest:
            self.dest = Path(self.dest).expanduser().resolve()
        if self.backup:
            self.backup = Path(self.backup).expanduser().resolve()
        self.translit = self.translit.lower().strip()

    @property
    def translit_enabled(self) -> bool:
        return self.translit in ("ja", "ko")


@dataclass
class Options:
    """CLI-only switches that map onto Config after parsing."""

    extra_args: list = field(default_factory=list)

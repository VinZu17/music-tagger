"""The run manifest: what was planned, what was applied, how to undo it.

The manifest is the safety net. Every planned rename is recorded with the name
it came from, so a run can be reversed per-file without a full restore.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Entry:
    """One file, as planned and (later) as applied."""

    old_name: str
    new_name: str = ""
    old_size: int = 0
    new_size: int = 0

    # what the filename parsed into
    parsed_artist: str = ""
    parsed_title: str = ""
    parsed_index: str = ""

    # what we resolved and wrote
    source: str = ""
    confidence: float = 0.0
    spotify_id: str = ""
    title: str = ""
    title_romanized: str = ""
    title_latin_alias: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    genre: str = ""
    date: str = ""
    track: str = ""
    total_tracks: str = ""
    lyrics: str = ""
    composer: str = ""
    cover_source: str = ""
    cover_bytes: int = 0
    comment: str = ""

    # origin of every decision, for the report
    notes: list = field(default_factory=list)
    applied: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def save(rows: list[Entry], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([r.to_dict() for r in rows], ensure_ascii=False, indent=1),
                    encoding="utf-8")


def load(path: Path) -> list[Entry]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Entry(**{k: v for k, v in row.items() if k in Entry.__dataclass_fields__})
            for row in raw]

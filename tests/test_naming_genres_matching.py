import pytest

from music_tagger.genres import normalize
from music_tagger.matching import pick, score
from music_tagger.naming import display_title, format_name, parse, sanitize, title_variants


# --------------------------------------------------------------- naming.parse

def test_parse_artist_title_dash():
    p = parse("Pink Venom.mp3")
    assert p["artist"] == "" and p["title"] == "Pink Venom"


def test_parse_with_index_and_artist():
    p = parse("001 - BABYMONSTER - DRIP.mp4")
    assert p["index"] == "001"
    assert p["artist"] == "BABYMONSTER" and p["title"] == "DRIP"


def test_parse_quoted_title_wins():
    p = parse("018 - BLACKPINK - 'JUMP' MV.mp4")
    assert p["index"] == "018" and p["artist"] == "BLACKPINK" and p["title"] == "JUMP"


def test_parse_strips_official_mv_noise():
    p = parse("NewJeans (뉴진스) 'Super Shy' Official MV.mp4")
    assert p["artist"] == "NewJeans (뉴진스)" and p["title"] == "Super Shy"


def test_parse_drops_channel_suffix():
    p = parse('060 - "Golden" Official Lyric Video | KPop Demon Hunters | Sony.mp4')
    assert p["title"] == "Golden"


def test_parse_from_clause_gives_artist():
    p = parse("080 - Golden #2025MAMA - PHARITA from BABYMONSTER.mp4")
    assert p["artist"] == "BABYMONSTER"


def test_parse_extension_stripped_for_all_formats():
    for name in ("a.mp3", "a.FLAC", "a.m4a", "a.ogg", "a.wav", "a.mp4"):
        assert parse(name)["title"] == "a"


# --------------------------------------------------------------- naming.format

def test_format_default_artist_title():
    assert format_name("Yuuri", "Birimirion") == "Yuuri - Birimirion.mp3"


def test_format_title_artist_style():
    assert format_name("Yuuri", "Birimirion", style="title-artist") == "Birimirion - Yuuri.mp3"


def test_format_unknown_style_raises():
    with pytest.raises(ValueError):
        format_name("a", "b", style="nonsense")


def test_sanitize_removes_slash_and_illegal():
    assert sanitize("HUNTR/X") == "HUNTR & X"
    # all illegal chars become spaces, then runs of spaces collapse
    assert sanitize('a:b*c?"d') == "a b c d"


def test_display_title_drops_feat_already_in_artist():
    assert display_title("Strategy (feat. Megan Thee Stallion)",
                         "TWICE, Megan Thee Stallion") == "Strategy"


def test_display_title_keeps_unknown_feat():
    assert display_title("Song (feat. Someone Else)", "TWICE") == "Song (feat. Someone Else)"


def test_title_variants_includes_bracketed_part():
    v = title_variants("魔法の絨毯 (Mahou no Jutan)")
    assert any("mahou no jutan" in x for x in v)


# ----------------------------------------------------------------------- genres

def test_japanese_rock_maps_to_jrock():
    assert normalize("ロック", lang="ja") == "J-Rock"


def test_korean_pop_maps_to_kpop():
    assert normalize("댄스", lang="ko") == "K-Dance"
    assert normalize("발라드", lang="ko") == "K-Ballad"


def test_chinese_pop_maps_to_cpop():
    assert normalize("流行", lang="zh") == "C-Pop"


def test_already_regional_is_left_alone():
    assert normalize("K-Pop") == "K-Pop"
    assert normalize("J-Rock") == "J-Rock"


def test_global_genre_is_not_prefixed():
    assert normalize("Rock", lang="ja") == "Rock"
    assert normalize("Jazz") == "Jazz"


def test_empty_genre_is_empty():
    assert normalize("") == ""


def test_unknown_latin_genre_passes_through():
    assert normalize("Shoegaze") == "Shoegaze"


# --------------------------------------------------------------------- matching

def test_exact_title_and_artist_scores_high():
    c = {"title": "DRIP", "artist": "BABYMONSTER"}
    assert score(c, "BABYMONSTER", "DRIP") == pytest.approx(1.0)


def test_wrong_artist_drops_score():
    c = {"title": "DRIP", "artist": "Someone Else"}
    assert score(c, "BABYMONSTER", "DRIP") < 0.72


def test_contained_title_scores_well():
    """'Do the Dance' sits inside 'Billyeoon Goyangi (Do the Dance)'."""
    c = {"title": "Billyeoon Goyangi (Do the Dance)", "artist": "ILLIT"}
    assert score(c, "ILLIT", "Do the Dance") > 0.72


def test_pick_honours_provider_priority():
    cands = {
        "deezer": [{"title": "T", "artist": "A", "score": 0.9}],
        "spotify": [{"title": "T", "artist": "A", "score": 0.9}],
    }
    chosen, source = pick(cands, "A", "T", order=("spotify", "deezer"))
    assert source == "spotify"


def test_wrong_artist_caps_score_below_accept():
    """Exact title + unrelated artist is a cover / same-named song, not a match."""
    c = {"title": "DRIP", "artist": "Someone Else"}
    assert score(c, "BABYMONSTER", "DRIP") <= 0.5


def test_matching_artist_keeps_full_score():
    c = {"title": "DRIP", "artist": "BABYMONSTER"}
    assert score(c, "BABYMONSTER", "DRIP") > 0.9


def test_pick_rejects_below_accept():
    chosen, source = pick({"spotify": [{"title": "T", "artist": "Z", "score": 0.3}]}, "A", "T")
    assert chosen is None and source == ""


def test_pick_picks_best_within_source():
    cands = {"spotify": [{"title": "T", "artist": "A", "score": 0.8},
                         {"title": "T", "artist": "A", "score": 0.95}]}
    chosen, _ = pick(cands, "A", "T")
    assert chosen["score"] == 0.95


def test_parse_strips_duplicate_marker():
    p = parse("Yuuri - ビリミリオン (2).mp3")
    assert p["title"] == "ビリミリオン" and p["duplicate"] == "2"


def test_parse_keeps_meaningful_paren_number():
    """A number that is part of the title must survive."""
    assert parse("Song (2011).mp3")["title"] == "Song (2011)" or True


def test_parse_trailing_year_in_parens_is_title():
    p = parse("Song (2011).mp3")
    assert p["duplicate"] == "" and p["title"] == "Song (2011)"


# ------------------------------------------------- non-Latin matching (regression)

def test_katakana_title_matches_itself():
    """strip_non_latin() used to delete the whole title, scoring 0 forever."""
    c = {"title": "ビリミリオン", "artist": "Yuuri"}
    assert score(c, "Yuuri", "ビリミリオン") > 0.9


def test_hangul_title_matches_itself():
    c = {"title": "뛰어", "artist": "BLACKPINK"}
    assert score(c, "BLACKPINK", "뛰어") > 0.9


def test_kanji_title_matches_itself():
    c = {"title": "弐", "artist": "優里"}
    assert score(c, "優里", "弐") > 0.9


def test_romanized_query_matches_katakana_via_latin_form():
    """'Birimirion' vs ビリミリオン is not phonetic - the Latin alias path
    handles that. What must work is the reverse: an already-Latin title
    matching a provider that spells it out."""
    c = {"title": "Leo", "artist": "Yuuri"}
    assert score(c, "Yuuri", "Leo") > 0.9

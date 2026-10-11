import pytest

from music_tagger.translit import needs_latin_alias, romanize_title


def test_katakana_uses_published_latin_title():
    """ビリミリオン reads 'birimirion' but the release is 'Billimillion'."""
    assert romanize_title("ビリミリオン", latin_alias="Billimillion") == "Billimillion"


def test_katakana_without_alias_falls_back_to_romaji():
    assert romanize_title("レオン") == "Reon"


def test_katakana_alias_must_itself_be_latin():
    """A Japanese alias must not be adopted as the 'Latin' title."""
    assert romanize_title("レオン", latin_alias="レオン") == "Reon"


def test_kanji_is_romanized_even_with_alias():
    """Kanji/hiragana is native Japanese - it gets romanized, not replaced."""
    assert romanize_title("恋人じゃなくなった日", latin_alias="whatever") == "Koibito janakunatta nichi"


def test_hiragana_only():
    assert romanize_title("かくれんぼ") == "Kakurenbo"


def test_latin_title_untouched():
    assert romanize_title("Pink Venom", latin_alias="Anything Else") == "Pink Venom"


def test_korean_romanized():
    pytest.importorskip("korean_romanizer")
    # 뛰어 -> "ttwieo": ㄸ is the tensed t (double), not ㄷ/d
    assert romanize_title("뛰어", lang="ko") == "ttwieo"


def test_korean_romanizer_missing_returns_input():
    from unittest import mock
    with mock.patch("music_tagger.translit._romanizer_available", return_value=False):
        assert romanize_title("뛰어", lang="ko") == "뛰어"


def test_empty_and_none_safe():
    assert romanize_title("") == ""
    assert romanize_title(" ") == ""


def test_punctuation_and_spaces_are_not_copied_into_romaji():
    out = romanize_title("ビリミリオン！ ")
    assert out == "Birimirion!"


def test_needs_latin_alias_flag():
    assert needs_latin_alias("レオン")
    assert not needs_latin_alias("恋人じゃなくなった日")
    assert not needs_latin_alias("Pink Venom")


def test_whitespace_is_collapsed():
    assert romanize_title("レオン") == romanize_title("  レオン  ")

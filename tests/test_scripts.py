from music_tagger.scripts import compose


def test_ascii_latin():
    c = compose("Pink Venom")
    assert c.script == "latin"
    assert not c.has_cjk
    assert c.is_latin_only


def test_katakana_only_is_not_japanese():
    """Katakana is the loanword script - it must NOT read as native Japanese."""
    c = compose("レオン")
    assert c.katakana == 3
    assert c.is_katakana_only
    assert not c.has_japanese


def test_kanji_is_japanese():
    assert compose("壱").has_japanese
    assert not compose("壱").is_katakana_only


def test_hiragana_is_japanese():
    assert compose("かくれんぼ").has_japanese


def test_mixed_kanji_hiragana():
    c = compose("恋人じゃなくなった日")
    assert c.has_japanese
    assert not c.is_katakana_only
    assert c.script == "japanese"


def test_korean():
    c = compose("뛰어")
    assert c.script == "korean"
    assert c.has_korean
    assert not c.has_cjk


def test_cyrillic_beats_latin():
    c = compose("Юлия Yuuri")
    assert c.script == "cyrillic"


def test_empty_and_punctuation_only():
    assert compose("").script == "digits"
    assert compose("--- !!! ???")


def test_digits_punctuation_is_ignored():
    c = compose("01 - Intro")
    assert c.script == "latin"
    assert c.digits == 2

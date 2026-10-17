"""Tests de la logique pure (aucun GPU, aucun modèle requis)."""
from app.summarize import chunks, clean, looks_french, norm, quote_ok, romaji_to_kana


def test_kana_basic():
    assert romaji_to_kana("Naruto wa oishii ramen o taberu") == "なると は おいしい らめん を たべる"
    assert romaji_to_kana("Hon o yomu") == "ほん を よむ"
    assert romaji_to_kana("tenki wa yokunai desu") == "てんき は よくない です"


def test_kana_combined_syllables():
    assert romaji_to_kana("daisuki janai") == "だいすき じゃない"
    assert romaji_to_kana("kyou") == "きょう"
    assert romaji_to_kana("shashin") == "しゃしん"
    assert romaji_to_kana("chotto matte") == "ちょっと まって"


def test_clean_removes_markdown_and_latex():
    assert clean("**gras** et $x$ $\\rightarrow$ fin") == "gras et x → fin"


def test_norm_strips_accents_and_punctuation():
    assert norm("Écoutez, ÇA va !") == "ecoutez ca va"


def test_looks_french():
    assert looks_french("Ça, c'est le TA.")
    assert looks_french("Je regarde des animés bizarres")
    assert not looks_french("Naruto wa oishii ramen o taberu")


def test_quote_validation_rejects_invented_sentences():
    lines = ["Sai wa omoi hon o kau", "Akai kuruma desu"]
    n_lines = [norm(x) for x in lines]
    n_all = " ".join(n_lines)
    assert quote_ok("Sai wa omoi hon o kau", n_lines, n_all)
    assert quote_ok("sai wa omoi hon wo kau", n_lines, n_all)       # variante proche acceptée
    assert not quote_ok("Tanaka sensei wa ii hito desu", n_lines, n_all)
    assert not quote_ok("Le temps est bon", n_lines, n_all)          # français rejeté


def test_chunks_cover_everything():
    lines = [str(i) for i in range(386)]
    parts = chunks(lines)
    assert sum(len(p) for p in parts) == 386
    assert [x for p in parts for x in p] == lines

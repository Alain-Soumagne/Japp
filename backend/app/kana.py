"""Comparaison tolérante de textes japonais : kana / romaji équivalents, ponctuation et voyelles longues ignorées."""
import re
import unicodedata

_PUNCT = re.compile(r"[\s、。，．,.!?！？「」『』\"'‘’“”・〜~…ー\-()（）:;：；]")
_JP = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_KANJI = re.compile(r"[\u4e00-\u9fff々]")


def has_japanese(s: str) -> bool:
    return bool(_JP.search(s or ""))


def has_kanji(s: str) -> bool:
    return bool(_KANJI.search(s or ""))


def kata_to_hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def loose(text: str) -> str:
    """Clé de comparaison : deux écritures d'un même mot (kana ou romaji) donnent la même clé."""
    from .summarize import romaji_to_kana
    s = unicodedata.normalize("NFKC", text or "").lower()
    if re.search(r"[a-zāīūēō]", s) and not has_japanese(s):
        s = romaji_to_kana(s)
    s = _PUNCT.sub("", kata_to_hira(s))
    s = s.replace("は", "わ").replace("を", "お").replace("へ", "え").replace("ぢ", "じ").replace("づ", "ず")
    # voyelles longues ignorées (les élèves omettent souvent les macrons) : こう = こ, かあ = か, きい = き…
    s = re.sub(r"([おこそとのほもよろをごぞどぼぽょ])[うお]", r"\1", s)
    s = re.sub(r"([うくすつぬふむゆるぐずづぶぷゅ])う", r"\1", s)
    s = re.sub(r"([あかさたなはまやらわがざだばぱゃ])あ", r"\1", s)
    s = re.sub(r"([いきしちにひみりぎじびぴ])い", r"\1", s)
    return re.sub(r"([えけせてねへめれげぜでべぺ])[えい]", r"\1", s)

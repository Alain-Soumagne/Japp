import random

import pytest

from app import exercises as ex
from app import levels

SYN = {"sections": [
    {"title": "Se présenter", "key_points": ["a", "b", "c", "d"], "examples": [
        {"japanese": "わたしは アレックスです。", "romaji": "Watashi wa Arekkusu desu.", "french": "Je suis Alex."},
        {"japanese": "おはようございます。", "romaji": "Ohayō gozaimasu.", "french": "Bonjour (le matin)."},
        {"japanese": "お名前は 何ですか。", "romaji": "O-namae wa nan desu ka.", "french": "Quel est votre nom ?"},
        {"japanese": "本を読みます。", "romaji": "Hon o yomimasu.", "french": "Je lis un livre."},
    ]}]}


# ------------------------------------------------------------ niveau et score
def q(d, verdict, **kw):
    return {"difficulty": d, "verdict": verdict, **kw}


def test_difficulte_exemple_croit_avec_longueur_et_kanji():
    assert levels.example_difficulty("おはよう") < levels.example_difficulty("おはようございます") < levels.example_difficulty("日本語学校で勉強しています")
    assert 1 <= levels.example_difficulty("") <= 10


def test_difficulte_cours_bornee():
    assert 1 <= levels.course_difficulty(SYN) <= 10
    assert levels.course_difficulty({}) == 2.0


def test_score_pondere_par_difficulte():
    facile_ok = [q(2, "correct"), q(8, "incorrect")]
    dur_ok = [q(2, "incorrect"), q(8, "correct")]
    assert levels.session_score(facile_ok) == 20.0
    assert levels.session_score(dur_ok) == 80.0
    assert levels.session_score([q(5, "partial")]) == 50.0
    assert levels.session_score([]) == 0.0


def test_question_exclue_ignoree():
    qs = [q(5, "correct"), q(5, "incorrect", excluded=True)]
    assert levels.session_score(qs) == 100.0


def test_niveau_monte_si_reussite_et_baisse_sinon():
    bon = [q(4.3, "correct") for _ in range(10)]
    mauvais = [q(4.3, "incorrect") for _ in range(10)]
    assert levels.next_level(4.0, bon) > 4.0
    assert levels.next_level(4.0, mauvais) < 4.0


def test_pas_de_mur_variation_limitee_par_session():
    parfait = [q(10, "correct") for _ in range(20)]
    nul = [q(1, "incorrect") for _ in range(20)]
    assert levels.next_level(3.0, parfait) - 3.0 <= levels.MAX_STEP + 1e-9
    assert 3.0 - levels.next_level(3.0, nul) <= levels.MAX_STEP + 1e-9


def test_session_courte_pese_moins():
    court = [q(6, "correct") for _ in range(2)]
    long_ = [q(6, "correct") for _ in range(8)]
    assert levels.level_delta(3.0, court) < levels.level_delta(3.0, long_)


def test_bornes_du_niveau():
    assert levels.next_level(9.9, [q(10, "correct") for _ in range(10)]) <= levels.LEVEL_MAX
    assert levels.next_level(1.0, [q(1, "incorrect") for _ in range(10)]) >= levels.LEVEL_MIN


def test_niveau_stable_quand_reussite_conforme_a_l_attendu():
    # 1 bonne réponse sur 2 à difficulté = niveau => attente 50 % => quasi aucun changement
    qs = [q(4.0, "correct"), q(4.0, "incorrect")] * 5
    assert abs(levels.level_delta(4.0, qs)) < 0.05


def test_progression_continue_sur_plusieurs_sessions():
    """Simule un élève de 'vrai niveau' 6 qui démarre à 2 : la montée est régulière, sans dépasser le palier."""
    rng, lvl, hist = random.Random(1), 2.0, []
    pool = [{"type": t, "difficulty": d / 4, "key": None} for d in range(4, 41) for t in ("mcq", "reading", "cloze")]
    for _ in range(40):
        qs = levels.select_questions(pool, 10, lvl, rng)
        for x in qs:
            x["verdict"] = "correct" if rng.random() < levels.expected_success(6.0, x["difficulty"]) else "incorrect"
        new = levels.next_level(lvl, qs)
        assert abs(new - lvl) <= levels.MAX_STEP + 1e-9
        lvl = new
        hist.append(lvl)
    assert hist[0] > 2.0 and 5.0 < hist[-1] < 7.2


def test_selection_suit_le_niveau_et_varie_les_types():
    pool = [{"type": t, "difficulty": d / 2, "key": f"{t}{d}"} for d in range(2, 21) for t in ("mcq", "reading", "cloze", "short")]
    bas = levels.select_questions(pool, 10, 2.0, random.Random(3))
    haut = levels.select_questions(pool, 10, 7.0, random.Random(3))
    assert sum(x["difficulty"] for x in haut) / 10 > sum(x["difficulty"] for x in bas) / 10 + 3
    assert len({x["type"] for x in bas}) >= 3
    assert len(levels.select_questions(pool[:3], 10, 4.0)) == 3


def test_libelles():
    assert levels.level_label(1.5) == "Débutant" and levels.level_label(10) == "Expert"


# ------------------------------------------------------------ questions et correction
def pool():
    return ex.questions_from_examples("j1", "Cours A", SYN, 4.0)


def by(t):
    return [x for x in pool() if x["type"] == t]


def test_questions_construites_depuis_les_exemples():
    types = {x["type"] for x in pool()}
    assert {"translate_ja_fr", "translate_fr_ja", "reading", "cloze"} <= types
    assert all(1 <= x["difficulty"] <= 10 for x in pool())


def test_cloze_prudent_une_seule_particule():
    c = by("cloze")
    assert any(x["reference"] == "は" and x["prompt"].startswith("わたし＿") for x in c)
    assert not any("＿" in x["prompt"] and x["prompt"].count("＿") != 1 for x in c)
    # 本を読みます : を repéré grâce au « o » isolé du romaji
    assert any(x["reference"] == "を" for x in c)


@pytest.mark.parametrize("rep", ["wa", "ha", "は", "ハ"])
def test_cloze_accepte_romaji_et_kana(rep):
    qq = next(x for x in by("cloze") if x["reference"] == "は")
    assert ex.grade_auto(qq, rep)[0] == "correct"


def test_cloze_refuse_autre_particule():
    qq = next(x for x in by("cloze") if x["reference"] == "は")
    assert ex.grade_auto(qq, "ga")[0] == "incorrect"


@pytest.mark.parametrize("rep", ["Ohayō gozaimasu", "ohayou gozaimasu", "ohayo gozaimasu.", "おはようございます", "オハヨウゴザイマス"])
def test_lecture_tolerante(rep):
    qq = next(x for x in by("reading") if x["prompt"].startswith("おはよう"))
    assert ex.grade_auto(qq, rep)[0] == "correct"


def test_lecture_partielle_et_fausse():
    qq = next(x for x in by("reading") if x["prompt"].startswith("おはよう"))
    assert ex.grade_auto(qq, "ohayou gozaimas")[0] == "partial"
    assert ex.grade_auto(qq, "sayonara")[0] == "incorrect"


def test_traduction_fr_ja_romaji_ou_kana_sinon_laisse_au_modele():
    qq = next(x for x in by("translate_fr_ja") if x["prompt"].startswith("Bonjour"))
    assert ex.grade_auto(qq, "ohayō gozaimasu")[0] == "correct"
    assert ex.grade_auto(qq, "おはようございます。")[0] == "correct"
    assert ex.grade_auto(qq, "konnichiwa") is None          # formulation inconnue : jugée par le modèle


def test_traduction_ja_fr_toujours_jugee_par_le_modele():
    assert ex.grade_auto(by("translate_ja_fr")[0], "Je suis Alex") is None


def test_reponse_vide_incorrecte():
    assert ex.grade_auto(by("translate_ja_fr")[0], "  ")[0] == "incorrect"


def test_qcm():
    qq = {"type": "mcq", "accepted": ["2"], "reference": "bonne", "choices": ["a", "b", "bonne", "d"]}
    assert ex.grade_auto(qq, "2")[0] == "correct" and ex.grade_auto(qq, "1")[0] == "incorrect"


def test_secours_sans_modele():
    qq = by("translate_ja_fr")[0]
    assert ex._fuzzy(qq, "Je suis Alex.")[0] == "correct"
    assert ex._fuzzy(qq, "Il pleut des cordes")[0] == "incorrect"


def test_vue_publique_ne_divulgue_rien_avant_correction():
    qs = [dict(x, id=f"q{i}", answer="") for i, x in enumerate(pool()[:3])]
    s = {"id": "abc", "status": "ready", "questions": qs}
    for v in ex.public_view(s)["questions"]:
        assert not ({"reference", "accepted", "explanation", "verdict", "difficulty", "feedback"} & set(v))
    s["status"] = "graded"
    assert "reference" in ex.public_view(s)["questions"][0]


def test_quota_de_questions_du_modele_meme_a_bas_niveau():
    pool = [{"type": "reading", "difficulty": 1.0 + i / 10, "key": f"r{i}"} for i in range(20)]
    pool += [{"type": "mcq", "difficulty": 6.0, "key": None}] * 3 + [{"type": "short", "difficulty": 7.0, "key": None}] * 2
    chosen = ex.pick(pool, 8, 1.5)
    assert len(chosen) == 8 and sum(q["type"] in ("mcq", "short") for q in chosen) == 2


def test_pick_sans_question_du_modele():
    pool = [{"type": "reading", "difficulty": 2.0, "key": f"r{i}"} for i in range(10)]
    assert len(ex.pick(pool, 6, 2.0)) == 6

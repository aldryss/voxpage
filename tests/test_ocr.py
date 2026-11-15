"""OCR des pages scannées : détection des pages sans texte, modes, repli, structure, et lecture réelle
(moteur et modèles dans ocr/, voir tools/fetch_ocr.py ; ces derniers tests sont sautés s'ils manquent)."""

import json
import re
import unicodedata
from pathlib import Path

import pytest

import voxpage.extract.pdf as pdf
from voxpage.extract import ExtractOptions, extractor_for, ocr
from voxpage.extract.ocr import OcrLine, OcrPage, fix_confusions, to_page_data
from voxpage.extract.pdf import _has_usable_text
from voxpage.extract.pdf_layout import PageData
from voxpage.extract.pdf_text import count_tokens
from voxpage.progress import Cancelled, CancelToken

CORPUS = Path(__file__).parent / "corpus"
needs_engine = pytest.mark.skipif(
    not ocr.available(), reason="moteur OCR ou modèles absents (python tools/fetch_ocr.py)"
)


def extract(name: str, **options):
    path = CORPUS / f"{name}.pdf"
    return extractor_for(path).extract(path, ExtractOptions(**options))


def texts(doc) -> list[str]:
    return [b.text for ch in doc.chapters for b in ch.blocks]


# ---------------------------------------------------------------------------------------------------------
# Moteur factice : lignes à des positions choisies


def fake_page(rows, x0=72.0, top=100.0, pitch=15.0, height=11.0, score=0.95, width=470.0) -> OcrPage:
    """Une ligne OCR par chaîne de `rows` ; une entrée None laisse un blanc d'un interligne."""
    lines, y = [], top
    for text in rows:
        if text is None:
            y += pitch
            continue
        full = not text.endswith((".", "!", "?", "»"))  # dernière ligne d'un paragraphe : plus courte
        lines.append(OcrLine(text, x0, y, x0 + (width if full else 5.2 * len(text)), y + height, score))
        y += pitch
    return OcrPage(595.0, 842.0, lines)


class FakeEngine:
    def __init__(self, pages: dict[int, OcrPage] | None = None, default: OcrPage | None = None, fail=()):
        self.pages = pages or {}
        self.default = default
        self.fail = set(fail)
        self.calls: list[tuple[int, str | None]] = []

    def __call__(self, path, index, lang):
        self.calls.append((index, lang))
        if index in self.fail:
            raise RuntimeError("panne simulée")
        return self.pages.get(index, self.default if self.default is not None else fake_page([]))


def with_engine(monkeypatch, engine):
    monkeypatch.setattr(pdf, "_ocr_engine", lambda: engine)
    return engine


SCAN_TEXT = fake_page(["Texte reconnu", "sur deux lignes.", None, "Second paragraphe."])


# ---------------------------------------------------------------------------------------------------------
# Détection d'une page sans texte exploitable


def page(**kw) -> PageData:
    base = {"index": 0, "width": 595.0, "height": 842.0, "frags": [], "segs": [], "fills": []}
    base.update(kw)
    return PageData(**base)


def test_page_normale_exploitable():
    assert _has_usable_text(page(n_chars=900, n_alnum=700, n_words=150, n_junk=3))


def test_page_blanche_exploitable():
    assert _has_usable_text(page())  # ni texte ni image : rien à reconnaître


def test_couche_vide_sous_une_image_est_inexploitable():
    full = 595.0 * 842.0
    assert not _has_usable_text(page(n_chars=2, n_alnum=2, image_area=0.9 * full))
    # un petit logo ne fait pas une page scannée
    assert _has_usable_text(page(n_chars=2, n_alnum=2, image_area=0.05 * full))


def test_glyphes_inconnus_inexploitable():
    assert not _has_usable_text(page(n_chars=100, n_alnum=90, n_unknown=60))
    assert _has_usable_text(page(n_chars=100, n_alnum=90, n_unknown=10))


def test_charabia_inexploitable():
    assert not _has_usable_text(page(n_chars=400, n_alnum=300, n_words=80, n_junk=60))
    assert _has_usable_text(page(n_chars=400, n_alnum=300, n_words=80, n_junk=20))
    assert _has_usable_text(page(n_chars=60, n_alnum=40, n_words=10, n_junk=9))  # trop court pour conclure


@pytest.mark.parametrize(
    ("text", "junk_share"),
    [
        ("Le conseil municipal s’est réuni le 14 mars à l’hôtel de ville et a voté la rénovation.", 0),
        ("The quick brown fox jumps over the lazy dog and runs through the forest", 0),
        ("Total 12 45 78 1,5 % 3 2 1 0,4 € ....... 12 ------ NASA SNCF RATP", 0),
        ("l l , . ' ' 1 i | ~ ; : l I , . - l i . ' , l l | . i ' , , l ; ; l . i l", 1),
        ("xqz kjhg wrtp bnmv zxcv qwrt pltk vbnm xcvb qsdf ghjk lmpn rtzp", 1),
        ("Le chÃ¢teau de l'Ã©glise est trÃ¨s Ã©lÃ©gant, dit-il Ã  son frÃ¨re", 0.4),
    ],
)
def test_comptage_du_charabia(text, junk_share):
    total, junk = count_tokens(text)
    assert total > 0
    if junk_share == 0:
        assert junk == 0
    else:
        assert junk / total >= min(junk_share, 0.4)


def test_couche_de_texte_incoherente_declenche_l_ocr(monkeypatch, tmp_path):
    """Un vrai PDF dont la couche de texte est du charabia : repéré par l'extracteur, confié à l'OCR."""
    garbage = "l l , . ' ' i | ~ ; : l I , . - l i . ' , l l | . i ' , , l ; ; l . i l " * 2
    engine = with_engine(monkeypatch, FakeEngine(default=SCAN_TEXT))
    from reportlab.pdfgen import canvas  # dépendance de test seulement

    path = tmp_path / "charabia.pdf"
    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 11)
    c.drawString(72, 700, garbage)
    c.showPage()
    c.save()
    doc = extractor_for(path).extract(path, ExtractOptions())
    assert [i for i, _ in engine.calls] == [0]
    assert texts(doc) == ["Texte reconnu sur deux lignes.", "Second paragraphe."]


# ---------------------------------------------------------------------------------------------------------
# Modes auto / always / never et repli


def test_auto_ne_lit_que_les_pages_sans_texte(monkeypatch):
    engine = with_engine(monkeypatch, FakeEngine(default=SCAN_TEXT))
    doc = extract("scan")  # page 1 native, page 2 scannée
    assert [i for i, _ in engine.calls] == [1]
    # (la page native d'une seule ligne pleine largeur se prolonge sur la page suivante, comme pour du natif)
    assert " ".join(texts(doc)) == (
        "Cette première page contient du texte natif. Texte reconnu sur deux lignes. Second paragraphe."
    )
    assert doc.warnings == ["Page 2 : texte reconnu par OCR, des erreurs de lecture sont possibles."]


def test_always_lit_toutes_les_pages(monkeypatch):
    engine = with_engine(monkeypatch, FakeEngine(default=SCAN_TEXT))
    doc = extract("scan", ocr="always")
    assert [i for i, _ in engine.calls] == [0, 1]
    assert doc.warnings == ["Pages 1 à 2 : texte reconnu par OCR, des erreurs de lecture sont possibles."]
    assert "Cette première page contient du texte natif." not in texts(doc)


def test_never_n_appelle_pas_le_moteur(monkeypatch):
    engine = with_engine(monkeypatch, FakeEngine(default=SCAN_TEXT))
    doc = extract("scan", ocr="never")
    assert engine.calls == []
    assert doc.warnings == ["Page 2 : aucun texte exploitable (page scannée ?)."]


def test_langue_transmise_au_moteur(monkeypatch):
    engine = with_engine(monkeypatch, FakeEngine(default=SCAN_TEXT))
    extract("scan")
    assert engine.calls == [(1, "fr")]  # langue du texte natif de la page 1


def test_sans_moteur_comportement_inchange(monkeypatch):
    monkeypatch.setattr(pdf, "_ocr_engine", lambda: None)
    doc = extract("scan")
    assert texts(doc) == ["Cette première page contient du texte natif."]
    assert doc.warnings == [
        "Page 2 : aucun texte exploitable (page scannée ?). "
        "La reconnaissance de caractères (OCR) n'est pas disponible : contenu ignoré."
    ]
    doc = extract("scan", ocr="always")
    assert texts(doc) == ["Cette première page contient du texte natif."]
    assert doc.warnings == [
        "La reconnaissance de caractères (OCR) n'est pas disponible : texte natif utilisé."
    ]


def test_modeles_absents_equivaut_a_sans_moteur(monkeypatch, tmp_path):
    monkeypatch.setenv("VOXPAGE_OCR", str(tmp_path))  # dossier vide
    assert not ocr.available()
    assert pdf._ocr_engine() is None
    doc = extract("scan")
    assert "n'est pas disponible" in doc.warnings[0]


def test_import_absent_equivaut_a_sans_moteur(monkeypatch):
    real = ocr.importlib.util.find_spec

    def find_spec(name, *args):
        return None if name == "rapidocr" else real(name, *args)

    monkeypatch.setattr(ocr.importlib.util, "find_spec", find_spec)
    assert not ocr.available()


def test_echec_du_moteur_sur_une_page_ne_plante_pas(monkeypatch):
    with_engine(monkeypatch, FakeEngine(default=SCAN_TEXT, fail={1}))
    doc = extract("scan")
    assert texts(doc) == ["Cette première page contient du texte natif."]
    assert any("la reconnaissance de caractères a échoué" in w for w in doc.warnings)


def test_echec_en_mode_always_garde_le_texte_natif(monkeypatch):
    with_engine(monkeypatch, FakeEngine(default=SCAN_TEXT, fail={0}))
    doc = extract("scan", ocr="always")
    assert "Cette première page contient du texte natif." in texts(doc)
    assert "Texte reconnu sur deux lignes." in texts(doc)


def test_page_sans_texte_reconnu_signalee(monkeypatch):
    with_engine(monkeypatch, FakeEngine(default=fake_page([])))
    doc = extract("scan")
    assert doc.warnings == ["Page 2 : aucun texte reconnu par l'OCR."]


def test_document_entierement_scanne_sans_texte_reconnu_est_une_erreur(monkeypatch):
    from voxpage.extract import ExtractError

    with_engine(monkeypatch, FakeEngine(default=fake_page([])))
    with pytest.raises(ExtractError, match="document scanné"):
        extract("scan", pages="2")


def test_faible_confiance_signalee_mais_texte_conserve(monkeypatch):
    low = fake_page(["Texte douteux mais conservé", "jusqu'au bout."], score=0.4)
    with_engine(monkeypatch, FakeEngine(default=low))
    doc = extract("scan")
    assert "Texte douteux mais conservé jusqu'au bout." in " ".join(texts(doc))
    assert any("lecture peu fiable" in w for w in doc.warnings)


def test_progression_et_annulation(monkeypatch):
    with_engine(monkeypatch, FakeEngine(default=SCAN_TEXT))
    steps: list[tuple[str, float]] = []
    extract_path = CORPUS / "scan.pdf"
    extractor_for(extract_path).extract(
        extract_path, ExtractOptions(ocr="always"), progress=lambda s, f: steps.append((s, f))
    )
    fractions = [f for _, f in steps]
    assert fractions == sorted(fractions) and fractions[0] == 0.0 and fractions[-1] == 1.0
    labels = [s for s, _ in steps]
    assert "Reconnaissance de caractères, page 1" in labels
    assert "Reconnaissance de caractères, page 2" in labels

    engine = FakeEngine(default=SCAN_TEXT)
    with_engine(monkeypatch, engine)
    token = CancelToken()

    def cancel_after_first_page(step, frac):
        if step == "Reconnaissance de caractères, page 1":
            token.cancel()

    with pytest.raises(Cancelled):
        extractor_for(extract_path).extract(
            extract_path, ExtractOptions(ocr="always"), cancel_after_first_page, token
        )
    assert len(engine.calls) == 1  # annulé avant la lecture de la deuxième page


# ---------------------------------------------------------------------------------------------------------
# Structure des pages OCR : même traitement que le texte natif


def doc_from_pages(monkeypatch, pages: dict[int, OcrPage], source="deux_pages", **options):
    with_engine(monkeypatch, FakeEngine(pages=pages))
    return extract(source, ocr="always", **options)


def test_cesures_recollees_comme_le_texte_natif(monkeypatch):
    rows = [
        "La transcrip-",
        "tion du texte est fidèle ; on n'attend pas peut-",
        "être de réponse, ni d'arc-en-",
        "ciel.",
    ]
    doc = doc_from_pages(monkeypatch, {0: fake_page(rows), 1: fake_page(["Fin."])})
    assert texts(doc)[0] == (
        "La transcription du texte est fidèle ; on n'attend pas peut-être de réponse, ni d'arc-en-ciel."
    )


def test_en_tetes_et_numeros_de_page_repetes_supprimes(monkeypatch):
    def numbered(n, body):
        rows = ["Ville de Mortagne — Conseil 2024"] + [None] * 6 + body + [None] * 40 + [f"- {n} -"]
        return fake_page(rows, top=40.0, pitch=15.0)

    pages = {
        0: numbered(1, ["Premier paragraphe de la première page."]),
        1: numbered(2, ["Un paragraphe de la deuxième page."]),
    }
    doc = doc_from_pages(monkeypatch, pages)
    assert texts(doc) == ["Premier paragraphe de la première page.", "Un paragraphe de la deuxième page."]


def test_paragraphes_separes_par_interligne(monkeypatch):
    rows = ["Premier paragraphe sur", "deux lignes.", None, "Deuxième paragraphe.", None, "Troisième."]
    rows += [None, "Fin."]
    doc = doc_from_pages(monkeypatch, {0: fake_page(rows), 1: fake_page(["Page deux."])})
    assert texts(doc)[:3] == ["Premier paragraphe sur deux lignes.", "Deuxième paragraphe.", "Troisième."]


def test_deux_colonnes_lues_dans_l_ordre(monkeypatch):
    left = [OcrLine(t, 72, 100 + 15 * i, 270, 111 + 15 * i, 0.9) for i, t in enumerate(
        ["Colonne de gauche, ligne un", "Colonne de gauche, ligne deux", "Colonne de gauche, ligne trois"]
    )]
    right = [OcrLine(t, 320, 100 + 15 * i, 520, 111 + 15 * i, 0.9) for i, t in enumerate(
        ["Colonne de droite, ligne un", "Colonne de droite, ligne deux", "Colonne de droite, ligne trois"]
    )]
    two = OcrPage(595.0, 842.0, left + right)
    doc = doc_from_pages(monkeypatch, {0: two, 1: fake_page(["Page deux."])})
    body = " ".join(texts(doc))
    assert body.index("gauche, ligne un") < body.index("gauche, ligne trois") < body.index("droite, ligne un")


def test_titre_plus_grand_reconnu(monkeypatch):
    lines = [OcrLine("Compte rendu", 72, 90, 250, 90 + 22, 0.9)]
    for n in range(8):
        text = f"Ligne de texte courant numéro {n} du document."
        lines.append(OcrLine(text, 72, 130 + 15 * n, 500, 141 + 15 * n, 0.9))
    doc = doc_from_pages(monkeypatch, {0: OcrPage(595.0, 842.0, lines), 1: fake_page(["Page deux."])})
    kinds = [(b.kind, b.text) for ch in doc.chapters for b in ch.blocks]
    assert any(kind == "heading" and text == "Compte rendu" for kind, text in kinds) or (
        doc.chapters[0].title == "Compte rendu"
    ), kinds


def test_taille_regularisee_malgre_boites_inegales():
    heights = [11, 14, 10, 13, 11, 12]  # accents et jambages font varier la boîte, pas la police
    lines = [
        OcrLine(f"ligne {i}", 72, 100 + 15 * i, 300, 100 + 15 * i + h, 0.9) for i, h in enumerate(heights)
    ]
    data = to_page_data(OcrPage(595.0, 842.0, lines), 0)
    assert len({round(f.size, 3) for f in data.frags}) == 1
    big = lines + [OcrLine("TITRE", 72, 300, 300, 300 + 24, 0.9)]
    sizes = {f.text: f.size for f in to_page_data(OcrPage(595.0, 842.0, big), 0).frags}
    assert sizes["TITRE"] > 1.5 * sizes["ligne 0"]


# ---------------------------------------------------------------------------------------------------------
# Corrections de confusions du moteur


@pytest.mark.parametrize(
    ("raw", "fixed"),
    [
        ("Ie chat et Ia souris", "Le chat et la souris"),
        ("I’hôtel de I'école", "l’hôtel de l'école"),
        ("aIors", "alors"),
        ("a déclaré Ia maire", "a déclaré la maire"),
        ("ll est venu. Ils Ie savent", "Il est venu. Ils le savent"),
        ("Il pleuvait. Ici, en Italie, IBM et l’IUT", "Il pleuvait. Ici, en Italie, IBM et l’IUT"),
    ],
)
def test_confusions_i_l(raw, fixed):
    assert fix_confusions(raw, "fr") == fixed


def test_confusions_ignorees_en_anglais():
    assert fix_confusions("I'm here, Ie", "en") == "I'm here, Ie"
    assert fix_confusions("I'm here") == "I'm here"  # apostrophe suivie d'une consonne : jamais corrigée


# ---------------------------------------------------------------------------------------------------------
# Lecture réelle (moteur et modèles présents)


def cer(ref: str, hyp: str, band: int = 80) -> float:
    """Taux d'erreur de caractères (Levenshtein dans une bande) sur textes aplatis."""

    def flat(t: str) -> str:
        t = unicodedata.normalize("NFC", t).translate(str.maketrans("’‘“”«»–—", "''\"\"\"\"--"))
        t = re.sub(r"\s+([!?;:%€°])", r"\1", t)
        t = re.sub(r"\s*\"\s*", '"', t)
        return re.sub(r"\s+", " ", t).strip()

    a, b = flat(ref), flat(hyp)
    n, m = len(a), len(b)
    inf = n + m + 1
    prev = {j: j for j in range(0, min(m, band) + 1)}
    for i in range(1, n + 1):
        cur = {}
        lo, hi = max(0, i - band), min(m, i + band)
        for j in range(lo, hi + 1):
            best = inf
            if j == 0:
                best = i
            else:
                best = min(best, cur.get(j - 1, inf) + 1)
                best = min(best, prev.get(j - 1, inf) + (a[i - 1] != b[j - 1]))
            best = min(best, prev.get(j, inf) + 1)
            cur[j] = best
        prev = cur
    return prev.get(m, inf) / max(1, n)


TRUTH = json.loads((CORPUS / "ocr.truth.json").read_text(encoding="utf-8"))


@needs_engine
def test_ocr_reel_du_pdf_scanne_du_corpus():
    doc = extract("scan")
    body = " ".join(texts(doc))
    assert doc.chapters and "Cette première page contient du texte natif." in texts(doc)
    for phrase in ("conseil municipal", "rénovation de l’école Jules-Ferry", "Hélène Garnier"):
        assert phrase.replace("’", "'") in body.replace("’", "'"), phrase
    assert doc.warnings == ["Page 2 : texte reconnu par OCR, des erreurs de lecture sont possibles."]


@needs_engine
@pytest.mark.parametrize(
    ("name", "max_cer"),
    [("ocr-roman", 0.03), ("ocr-journal", 0.02), ("ocr-colonnes", 0.03)],
)
def test_ocr_reel_pages_du_banc_d_essai(name, max_cer):
    doc = extract(name)
    got = "\n\n".join(texts(doc))
    error = cer(TRUTH[name], got)
    assert error <= max_cer, f"CER {error:.2%} > {max_cer:.0%}\n{got}"


@needs_engine
def test_ocr_reel_en_tetes_et_numeros_retires():
    doc = extract("ocr-entetes")
    body = "\n".join(texts(doc))
    assert "Mortagne" not in body, body
    assert not re.search(r"-\s*[123]\s*-", body), body
    error = cer(TRUTH["ocr-entetes"], "\n\n".join(texts(doc)))
    assert error <= 0.03, f"CER {error:.2%}\n{body}"
    assert {b.page for ch in doc.chapters for b in ch.blocks} == {1, 2, 3}

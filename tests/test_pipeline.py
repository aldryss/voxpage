import numpy as np
import pytest

from voxpage import pipeline
from voxpage.extract import UnsupportedFormat  # noqa: F401
from voxpage.normalize.lexicon import LexiconSource
from voxpage.pipeline import ConversionError, convert, extract_text
from voxpage.progress import Cancelled, CancelToken
from voxpage.settings import Settings
from voxpage.tts.base import Voice

RATE = 16000
FR = (
    "Bonjour tout le monde. Ceci est la première phrase du document.\n\n"
    "Et voici la suite, pour le deuxième paragraphe."
)


class FakeEngine:
    def __init__(self, voices=None, fail_on=None, fail_times=1, on_call=None):
        self.voices = voices or [Voice("en_x", "Anglais", "en"), Voice("fr_x", "Français", "fr")]
        self.fail_on, self.fail_times, self.on_call = fail_on, fail_times, on_call
        self.calls = []

    def list_voices(self):
        return self.voices

    def synthesize(self, text, voice_id, speaker=0, speed=1.0):
        self.calls.append((text, voice_id))
        if self.on_call:
            self.on_call(len(self.calls))
        if self.fail_on and self.fail_on in text and self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("boum")
        n = int(RATE * 0.01 * len(text))
        t = np.arange(n) / RATE
        return (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16), RATE


@pytest.fixture
def doc(tmp_path):
    p = tmp_path / "livre.txt"
    p.write_text(FR, encoding="utf-8")
    return p


def settings(**kw):
    s = Settings(voice_id="fr_x")
    s.audio.format = "wav"
    for k, v in kw.items():
        setattr(s.audio, k, v)
    return s


def test_fichier_unique(doc, tmp_path):
    out = tmp_path / "sortie.wav"
    r = convert(doc, out, settings(), engine=FakeEngine())
    assert r.files == [out] and out.is_file() and r.duration_s > 1
    assert not list(tmp_path.glob("*.part"))


def test_progression_monotone(doc, tmp_path):
    seen = []
    convert(
        doc,
        tmp_path / "o.wav",
        settings(),
        progress=lambda label, f: seen.append((label, f)),
        engine=FakeEngine(),
    )
    fr = [f for _, f in seen]
    assert fr == sorted(fr) and fr[0] == 0.0 and fr[-1] == 1.0
    assert all(isinstance(label, str) and label for label, _ in seen)
    assert any(label.startswith("Synthèse vocale") for label, _ in seen)


def test_par_chapitres(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("Une phrase simple.", encoding="utf-8")
    from voxpage.document import Block, Chapter, Document

    class Ext:
        extensions = (".chap",)

        def extract(self, path, options, progress=None, cancel=None):
            return Document(
                "T",
                "A",
                "fr",
                [
                    Chapter("Un", [Block("paragraph", "Alpha beta.")]),
                    Chapter("Deux", [Block("paragraph", "Gamma delta.")]),
                ],
                ["avert"],
            )

    from voxpage import extract

    extract.register(Ext())
    src = tmp_path / "x.chap"
    src.write_text("x")
    labels = []
    r = convert(
        src,
        tmp_path / "out",
        settings(split="chapters"),
        progress=lambda a, b: labels.append(a),
        engine=FakeEngine(),
    )
    names = sorted(f.name for f in r.files)
    assert sum(n.endswith(".wav") for n in names) == 2 and any(n.endswith(".m3u8") for n in names)
    assert any("chapitre 2 sur 2" in label for label in labels)
    assert r.warnings == ["avert"]


def test_annulation_sans_residu(doc, tmp_path):
    token = CancelToken()
    eng = FakeEngine(on_call=lambda n: token.cancel() if n == 2 else None)
    out = tmp_path / "sortie" / "o.wav"
    with pytest.raises(Cancelled):
        convert(doc, out, settings(), cancel=token, engine=eng)
    assert not out.exists() and not list(out.parent.glob("*")) if out.parent.exists() else True
    assert [p.name for p in tmp_path.iterdir()] == ["livre.txt"]


def test_voix_inconnue(doc, tmp_path):
    s = settings()
    s.voice_id = "nope"
    with pytest.raises(ConversionError, match="nope"):
        convert(doc, tmp_path / "o.wav", s, engine=FakeEngine())
    assert not (tmp_path / "o.wav").exists()


def test_document_vide(tmp_path):
    p = tmp_path / "v.txt"
    p.write_text("  \n\n ", encoding="utf-8")
    with pytest.raises(ConversionError, match="aucun texte"):
        convert(p, tmp_path / "o.wav", settings(), engine=FakeEngine())


def test_entree_absente_et_format_inconnu(tmp_path):
    with pytest.raises(ConversionError, match="introuvable"):
        convert(tmp_path / "x.txt", tmp_path / "o.wav", settings(), engine=FakeEngine())
    (tmp_path / "x.zzz").write_text("a")
    with pytest.raises(ConversionError, match="non pris en charge"):
        convert(tmp_path / "x.zzz", tmp_path / "o.wav", settings(), engine=FakeEngine())


def test_sortie_non_inscriptible(doc, tmp_path):
    (tmp_path / "dossier").mkdir()
    with pytest.raises(ConversionError, match="dossier"):
        convert(doc, tmp_path / "dossier", settings(), engine=FakeEngine())


def test_avertissement_de_langue(doc, tmp_path):
    s = settings()
    s.voice_id = "en_x"
    eng = FakeEngine()
    r = convert(doc, tmp_path / "o.wav", s, engine=eng)
    assert any("langue" in w for w in r.warnings)
    assert {v for _, v in eng.calls} == {"en_x"}


def test_voix_par_defaut(doc, tmp_path):
    s = settings()
    s.voice_id = ""
    eng = FakeEngine()
    r = convert(doc, tmp_path / "o.wav", s, engine=eng)
    assert {v for _, v in eng.calls} == {"fr_x"} and not r.warnings
    eng = FakeEngine(voices=[Voice("en_x", "A", "en")])
    r = convert(doc, tmp_path / "o2.wav", s, engine=eng)
    assert {v for _, v in eng.calls} == {"en_x"}


def test_echec_unique_puis_reussite(doc, tmp_path):
    eng = FakeEngine(fail_on="deuxième", fail_times=1)
    convert(doc, tmp_path / "o.wav", settings(), engine=eng)
    assert sum("deuxième" in t for t, _ in eng.calls) == 2


def test_echec_persistant_cite_le_passage(doc, tmp_path):
    eng = FakeEngine(fail_on="deuxième", fail_times=9)
    with pytest.raises(ConversionError, match="deuxième"):
        convert(doc, tmp_path / "o.wav", settings(), engine=eng)
    assert [p.name for p in tmp_path.iterdir()] == ["livre.txt"]


def test_extract_text(doc):
    text = extract_text(doc, settings())
    lines = text.strip().splitlines()
    assert "Bonjour tout le monde." in lines
    assert any("deuxième paragraphe" in line for line in lines)
    assert pipeline.ConvertResult([], 0.0).warnings == []


@pytest.mark.voices
def test_bout_en_bout_mp3(tmp_path):
    from mutagen.mp3 import MP3

    p = tmp_path / "essai.txt"
    p.write_text(
        "Bonjour. Ceci est un test de la voix française. Il fait beau aujourd'hui.", encoding="utf-8"
    )
    s = Settings(voice_id="fr_FR-siwis-medium")
    out = tmp_path / "essai.mp3"
    r = convert(p, out, s)
    audio = MP3(out)
    assert 3 < audio.info.length < 25
    assert abs(audio.info.length - r.duration_s) < 0.5
    assert audio.tags is not None and "TIT2" in audio.tags


# --- recette de bout en bout (issue #11) ------------------------------------------------------------------


def _register(ext_name, extract):
    from voxpage import extract as registry

    class Ext:
        extensions = (ext_name,)

        def extract(self, path, options, progress=None, cancel=None):
            return extract(path)

    registry.register(Ext())


def test_erreur_extraction_sans_repetition(tmp_path):
    from voxpage.extract.base import ExtractError

    def boom(path):
        raise ExtractError(f"« {path.name} » est protégé par un mot de passe.")

    _register(".prot", boom)
    src = tmp_path / "x.prot"
    src.write_text("x")
    with pytest.raises(ConversionError) as err:
        extract_text(src, settings())
    assert str(err.value) == "« x.prot » est protégé par un mot de passe."
    assert str(err.value).count("x.prot") == 1


def test_extract_text_titre_non_repete(tmp_path):
    from voxpage.document import Block, Chapter, Document

    _register(
        ".tit",
        lambda path: Document(
            "Livre",
            None,
            "fr",
            [
                Chapter(
                    "Chapitre 2,5 %", [Block("heading", "Chapitre 2,5 %", 1), Block("paragraph", "Texte.")]
                ),
                Chapter("Sans titre dans le texte", [Block("paragraph", "Suite.")]),
            ],
            [],
        ),
    )
    src = tmp_path / "x.tit"
    src.write_text("x")
    lines = extract_text(src, settings()).splitlines()
    assert lines[:2] == ["== Chapitre 2,5 % ==", "Texte."]
    # titre absent du texte : il est annoncé ; la ligne « == … == » tient lieu de cette annonce
    assert lines[3:5] == ["== Sans titre dans le texte ==", "Suite."]
    assert "Sans titre dans le texte" not in lines


def test_titre_apres_surtitre_dit_une_fois(tmp_path):
    from voxpage.document import Block, Chapter, Document
    from voxpage.normalize import NormalizeOptions, normalize

    doc = Document(
        "Grand titre",
        None,
        "fr",
        [
            Chapter(
                "Grand titre",
                [
                    Block("heading", "BILAN 2024", 2),
                    Block("heading", "Grand titre", 1),
                    Block("paragraph", "Texte."),
                ],
            )
        ],
        [],
    )
    said = [s.text for s in normalize(doc, NormalizeOptions())[0].segments]
    assert said.count("Grand titre") == 1


def test_passage_muet_signale(doc, tmp_path):
    class Muet(FakeEngine):
        def synthesize(self, text, voice_id, speaker=0, speed=1.0):
            if "deuxième" in text:
                return np.zeros(0, dtype=np.int16), RATE
            return super().synthesize(text, voice_id, speaker, speed)

    r = convert(doc, tmp_path / "o.wav", settings(), engine=Muet())
    assert len(r.warnings) == 1
    assert "aucun son" in r.warnings[0] and "deuxième paragraphe" in r.warnings[0]


# --------------------------------------------------------------------------- dictionnaire de prononciation


@pytest.fixture
def sigle(tmp_path):
    p = tmp_path / "sigle.txt"
    p.write_text("Le rapport de la ZXQ est publié. Selon M. Nguyen.", encoding="utf-8")
    return p


def user_dico(tmp_path, text="ZXQ = zed ix qu\nNguyen = nou-yène\n"):
    f = tmp_path / "dico.txt"
    f.write_text(text, encoding="utf-8")
    return LexiconSource(user_path=f)


def test_extract_text_avec_dictionnaire(sigle, tmp_path):
    text = extract_text(sigle, settings(), pronunciations=user_dico(tmp_path))
    assert "Le rapport de la zed ix qu est publié." in text and "monsieur nou-yène." in text


def test_extract_text_sans_dictionnaire(sigle, tmp_path):
    text = extract_text(sigle, settings(), pronunciations=LexiconSource(shipped=False, user=False))
    assert "la Z X Q est publié" in text and "Nguyen" in text


def test_convert_synthetise_le_dit(sigle, tmp_path):
    engine = FakeEngine()
    convert(sigle, tmp_path / "s.wav", settings(), engine=engine, pronunciations=user_dico(tmp_path))
    said = " ".join(t for t, _ in engine.calls)
    assert "zed ix qu" in said and "Z X Q" not in said


def test_convert_signale_les_lignes_invalides(sigle, tmp_path):
    src = user_dico(tmp_path, "ZXQ = zed ix qu\nn'importe quoi\n")
    result = convert(sigle, tmp_path / "s.wav", settings(), engine=FakeEngine(), pronunciations=src)
    assert any("ligne 2 ignorée" in w and "dico.txt" in w for w in result.warnings)
    warnings: list[str] = []
    extract_text(sigle, settings(), warnings=warnings, pronunciations=src)
    assert any("ligne 2 ignorée" in w for w in warnings)


def test_dictionnaire_de_la_langue_du_document(tmp_path):
    f = tmp_path / "dico.txt"
    f.write_text("[fr]\nZXQ = en français\n[en]\nZXQ = in english\n", encoding="utf-8")
    en = tmp_path / "en.txt"
    en.write_text("The report of the ZXQ is out. It is the ZXQ, and this is the end of it.", encoding="utf-8")
    text = extract_text(en, settings(), pronunciations=LexiconSource(user_path=f))
    assert "in english" in text and "en français" not in text


def test_utilisateur_par_defaut_a_cote_des_reglages(sigle, tmp_path, monkeypatch):
    from voxpage import settings as app_settings

    monkeypatch.setattr(app_settings, "app_dir", lambda: tmp_path / "app")
    monkeypatch.setattr(app_settings, "fallback_dir", lambda: tmp_path / "fb")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "prononciations.txt").write_text("ZXQ = zed ix qu\n", encoding="utf-8")
    assert "zed ix qu" in extract_text(sigle, settings())

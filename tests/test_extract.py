from pathlib import Path

import pytest

from voxpage import extract
from voxpage.extract import ExtractOptions, UnsupportedFormat, extractor_for, supported_extensions


def test_txt_enregistre_par_defaut():
    assert ".txt" in supported_extensions()
    assert extractor_for(Path("A.TXT")).extensions == (".txt",)


def test_format_inconnu():
    with pytest.raises(UnsupportedFormat):
        extractor_for(Path("livre.xyz"))


def test_register_nouvel_extracteur():
    class Fake:
        extensions = (".fake",)

    fake = Fake()
    extract.register(fake)
    try:
        assert extractor_for(Path("x.fake")) is fake
    finally:
        extract._registry.pop(".fake")


def extraire(tmp_path, data: bytes, name="note.txt"):
    p = tmp_path / name
    p.write_bytes(data)
    return extractor_for(p).extract(p, ExtractOptions())


def test_txt_paragraphes(tmp_path):
    doc = extraire(tmp_path, "Premier\nparagraphe.\n\n\nSecond  paragraphe.\r\n\r\nTroisième.".encode())
    assert doc.title == "note"
    assert doc.author is None
    assert len(doc.chapters) == 1 and doc.chapters[0].title == ""
    assert [b.text for b in doc.chapters[0].blocks] == [
        "Premier paragraphe.",
        "Second paragraphe.",
        "Troisième.",
    ]
    assert all(b.kind == "paragraph" for b in doc.chapters[0].blocks)


@pytest.mark.parametrize(
    "data",
    ["Été à Noël".encode("utf-8-sig"), "Été à Noël".encode(), "Été à Noël".encode("cp1252")],
)
def test_txt_encodages(tmp_path, data):
    assert extraire(tmp_path, data).chapters[0].blocks[0].text == "Été à Noël"


def test_txt_langue(tmp_path):
    assert extraire(tmp_path, b"The cat is on the mat and it is happy.").lang == "en"
    assert extraire(tmp_path, b"Le chat est sur le tapis et il est content.").lang == "fr"


def test_txt_vide(tmp_path):
    assert extraire(tmp_path, b"").chapters[0].blocks == []

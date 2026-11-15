from voxpage.lang import detect_lang


def test_francais():
    assert detect_lang("Il était une fois une princesse qui vivait dans un grand château.") == "fr"


def test_anglais():
    assert detect_lang("Once upon a time there was a princess who lived in a big castle.") == "en"


def test_vide_par_defaut_francais():
    assert detect_lang("") == "fr"

"""Noms de fichiers sûrs pour Windows."""

import re

MAX_TITLE_LEN = 80

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])$", re.IGNORECASE)


def clean_name(text: str, fallback: str, max_len: int = MAX_TITLE_LEN) -> str:
    """Nettoie `text` pour en faire un nom de fichier (sans extension) valide sous Windows.

    Les caractères interdits deviennent « _ », les espaces sont normalisés, les points et espaces
    finaux supprimés, les noms réservés (CON, PRN, COM1…) protégés et la longueur limitée.
    Un texte vide après nettoyage donne `fallback`.
    """
    name = _FORBIDDEN.sub("_", re.sub(r"[\t\n\r\f\v]+", " ", text or ""))
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
    if not name.strip("_ ."):
        return fallback
    if _RESERVED.match(name.split(".")[0].rstrip(" ")):
        name = "_" + name
    return name

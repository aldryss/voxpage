"""Sélection de pages : « 1-10,15 », « 3- », « -5 »."""

import re

_PART = re.compile(r"^(\d*)\s*-\s*(\d*)$|^(\d+)$")


def parse_pages(spec: str | None, count: int) -> list[int]:
    """Renvoie les index (à partir de 0) des pages choisies, triés et sans doublon.

    Lève ValueError avec un message en français si la sélection est invalide ou vide.
    """
    if spec is None or not spec.strip():
        return list(range(count))
    chosen: set[int] = set()
    for part in spec.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        m = _PART.match(part)
        if not m:
            raise ValueError(f"Sélection de pages invalide : « {part} ». Exemple attendu : 1-10,15.")
        if m.group(3):
            first = last = int(m.group(3))
        else:
            first = int(m.group(1)) if m.group(1) else 1
            last = int(m.group(2)) if m.group(2) else count
            if not m.group(1) and not m.group(2):
                raise ValueError(f"Sélection de pages invalide : « {part} ».")
        if first < 1 or last < first:
            raise ValueError(f"Sélection de pages invalide : « {part} ».")
        chosen.update(range(first - 1, min(last, count)))
    if not chosen:
        raise ValueError(
            f"Aucune page sélectionnée : le document compte {count} page{'s' if count > 1 else ''}."
        )
    return sorted(chosen)

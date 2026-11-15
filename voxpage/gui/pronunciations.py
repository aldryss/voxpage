"""Logique du dialogue « Prononciations », sans dépendance à wx (testable partout)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from voxpage.normalize import lexicon as lx
from voxpage.normalize.text import speak

LANG_CHOICES = (("", "Toutes les langues"), ("fr", "Français"), ("en", "Anglais"))
LANG_NAMES = {"": "toutes", "fr": "français", "en": "anglais"}

# Libellés du dialogue (accélérateur &) : uniques dans le dialogue, clés préfixées « pron_ ».
LABELS = {
    "pron_list": "&Entrées de l'utilisateur",
    "pron_written": "É&crit",
    "pron_spoken": "&Dit",
    "pron_lang": "&Langue",
    "pron_add": "&Ajouter",
    "pron_modify": "&Modifier",
    "pron_delete": "&Supprimer",
    "pron_listen": "Éco&uter",
    "pron_listen_raw": "Écouter sans le dic&tionnaire",
    "pron_status": "&Résultat",
    "pron_open": "&Ouvrir le fichier",
    "pron_close": "&Fermer",
}

HELP = (
    "Écrit : le mot, le sigle ou l'expression tel qu'il est écrit dans le document. "
    "Dit : ce que la voix doit lire, en lettres ordinaires (par exemple « EDF » se dit « eu dé effe »). "
    "Un écrit tout en minuscules ignore la casse. Un dit vide annule l'entrée livrée avec Voxpage."
)


@dataclass(frozen=True)
class Row:
    line: int
    written: str
    spoken: str
    lang: str

    @property
    def lang_name(self) -> str:
        return LANG_NAMES.get(self.lang, self.lang)

    @property
    def spoken_display(self) -> str:
        return self.spoken or "(annule l'entrée livrée)"


class PronunciationModel:
    """Dictionnaire de l'utilisateur : lecture, ajout, modification, suppression (enregistrés aussitôt)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.file = lx.LexiconFile(self.path)
        self._mtime = self._stat()

    def _stat(self) -> float | None:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    # -- lecture
    def rows(self) -> list[Row]:
        return [Row(e.line, e.written, e.spoken, e.lang) for e in self.file.entries]

    def row_at(self, line: int) -> Row | None:
        return next((r for r in self.rows() if r.line == line), None)

    def problems(self) -> list[str]:
        return [str(p) for p in self.file.problems]

    def changed_on_disk(self) -> bool:
        return self._stat() != self._mtime

    def reload(self) -> None:
        self.file.reload()
        self._mtime = self._stat()

    # -- modification : chaque opération enregistre, et renvoie le message annoncé à l'utilisateur
    def _save(self) -> None:
        self.file.save()
        self._mtime = self._stat()

    def add(self, written: str, spoken: str, lang: str = "") -> str:
        self.file.add(written, spoken, lang)
        self._save()
        return f"« {written.strip()} » ajouté."

    def update(self, line: int, written: str, spoken: str, lang: str = "") -> str:
        self.file.update(line, written, spoken, lang)
        self._save()
        return f"« {written.strip()} » modifié."

    def remove(self, line: int) -> str:
        row = self.row_at(line)
        self.file.remove(line)
        self._save()
        return f"« {row.written if row else 'Entrée'} » supprimé."

    def ensure_file(self) -> Path:
        """Crée le fichier (avec son en-tête explicatif) s'il n'existe pas, pour l'ouvrir dans un éditeur."""
        if not self.path.is_file():
            self._save()
        return self.path

    # -- écoute
    @staticmethod
    def listen_text(written: str, spoken: str, with_dictionary: bool, lang: str = "fr") -> str:
        """Texte à synthétiser : le « dit » tel quel, ou l'écrit tel que lu sans dictionnaire."""
        if with_dictionary:
            return spoken.strip()
        return speak(written.strip(), "en" if lang == "en" else "fr")

    @staticmethod
    def confirm_delete_text(row: Row) -> str:
        return f"Supprimer « {row.written} » du dictionnaire ?"

    def summary(self) -> str:
        n = len(self.rows())
        text = "Aucune entrée." if n == 0 else (f"{n} entrée." if n == 1 else f"{n} entrées.")
        problems = self.problems()
        if problems:
            text += f" {len(problems)} ligne(s) ignorée(s) : " + " ; ".join(problems[:3])
        return text

"""Auto-test de l'interface : `python -m voxpage --gui-self-test` (exécuté par la CI Windows)."""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from voxpage.gui import model as m
from voxpage.gui.deps import GuiDeps


class SelfTestError(Exception):
    pass


def _check(cond: object, message: str) -> None:
    if not cond:
        raise SelfTestError(message)


class _FakeEngine:
    def list_voices(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(id="fr-test", name="Français — test", lang="fr", speakers=[]),
            SimpleNamespace(id="en-test", name="English — test", lang="en", speakers=["A", "B"]),
        ]

    def synthesize(self, text: str, voice_id: str, speaker: int = 0, speed: float = 1.0):
        return np.zeros(2205, dtype=np.int16), 22050


class _Recorder:
    def __init__(self) -> None:
        self.saved: list = []
        self.calls: list = []
        self.mode = "ok"

    def convert(self, input, output, settings, progress=None, cancel=None):  # noqa: A002
        self.calls.append((input, output, settings.voice_id, settings.audio.format))
        if self.mode == "ok":
            for i in range(0, 101, 5):
                progress("Synthèse vocale", i / 100)
            return SimpleNamespace(files=[Path(output)], duration_s=3725.0, warnings=["pages 4 à 9 : OCR"])
        if self.mode == "error":
            raise RuntimeError("détail technique interne")
        while True:  # mode "block" : attend l'annulation
            progress("Synthèse vocale", 0.2)
            time.sleep(0.01)
            cancel.raise_if_cancelled()

    def extract_text(self, input, settings, progress=None, cancel=None):  # noqa: A002
        progress("Lecture", 1.0)
        return "Texte extrait."


def wx_idle(app) -> None:
    import wx

    wx.WakeUpIdle()
    app.ProcessPendingEvents()


def _pump(app, cond: Callable[[], bool], timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.Yield(True)
        wx_idle(app)
        if cond():
            return True
        time.sleep(0.01)
    return False


def _check_accessibility(win) -> None:
    labels = [m.LABELS[k] for k in win.controls]
    dup = m.duplicate_accelerators(labels)
    _check(not dup, f"accélérateurs en double : {dup}")
    for key, ctrl in win.controls.items():
        name = ctrl.GetName().strip()
        _check(name, f"contrôle « {key} » sans nom accessible")
        _check(name.startswith(m.plain_label(m.LABELS[key])), f"nom inattendu pour « {key} » : {name!r}")
        if key in win.static_labels:
            lab = win.static_labels[key]
            order = win.created
            _check(order.index(ctrl) == order.index(lab) + 1, f"libellé de « {key} » mal placé")
    _check(win.gauge.GetName().strip(), "jauge sans nom")


def run_self_test() -> int:
    try:
        import wx

        from voxpage.gui.main_window import MainWindow

        _run(wx, MainWindow)
    except SelfTestError as exc:
        print(f"Échec de l'auto-test de l'interface : {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Échec de l'auto-test de l'interface : {type(exc).__name__} : {exc}")
        return 1
    print("Auto-test de l'interface : réussi.")
    return 0


def _run(wx, MainWindow) -> None:  # noqa: N803
    from voxpage.settings import Settings

    app = wx.App(False)
    rec = _Recorder()
    deps = GuiDeps(
        convert=lambda *a, **k: rec.convert(*a, **k),
        extract_text=rec.extract_text,
        engine_factory=_FakeEngine,
        extensions=lambda: [".pdf", ".txt"],
        load_settings=Settings,
        save_settings=rec.saved.append,
    )
    win = MainWindow(deps)
    errors: list[str] = []
    answers = {"confirm": True}
    win.show_error = errors.append
    win.confirm = lambda title, text: answers["confirm"]
    win.Show()
    app.Yield(True)

    _check_accessibility(win)
    _check(win.IsShown(), "fenêtre non affichée")
    _check(not win.convert_btn.IsEnabled(), "« Convertir » actif sans fichier")

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "exemple.txt"
        src.write_text("Bonjour.", encoding="utf-8")
        win.set_input(src)
        _check(Path(win.output_text.GetValue()) == Path(tmp) / "exemple.mp3", "sortie proposée incorrecte")
        _check(win.convert_btn.IsEnabled(), "« Convertir » inactif avec un fichier")

        # Changement de réglages : enregistrés, sortie re-proposée.
        win.format_choice.SetSelection(1)
        win._on_format_or_split(None)
        _check(rec.saved and rec.saved[-1].audio.format == "wav", "réglage non enregistré")
        _check(win.output_text.GetValue().endswith("exemple.wav"), "sortie non mise à jour")
        win.voice_choice.SetSelection(1)
        win._on_voice(None)
        _check(win.speaker_choice.IsEnabled() and win.speaker_choice.GetCount() == 2, "locuteurs absents")
        win.speed_slider.SetValue(12)
        win._on_speed(None)
        slider_name = win.speed_slider.GetName()
        _check(slider_name == "Vitesse : 1,2", f"nom du curseur : {slider_name}")
        win.voice_choice.SetSelection(0)
        win._on_voice(None)

        # Conversion réussie.
        win.start_conversion()
        _check(win.state is m.UiState.CONVERTING and win.cancel_btn.IsEnabled(), "état « conversion » absent")
        _check(not win.voice_choice.IsEnabled() and not win.convert_btn.IsEnabled(), "réglages actifs")
        _check(_pump(app, lambda: win.state is m.UiState.IDLE), "conversion non terminée")
        text = win.status_text.GetValue()
        _check("Conversion terminée" in text and "1 heure 2 minutes 5 secondes" in text, "résultat : " + text)
        _check("pages 4 à 9" in text, "avertissement absent")
        _check(win.open_btn.IsEnabled(), "« Ouvrir le dossier » inactif")
        _check(rec.calls and rec.calls[-1][2] == "fr-test" and rec.calls[-1][3] == "wav", "appel incorrect")
        _check(win.gauge.GetValue() == 100, "jauge incomplète")

        # Erreur : message français, pas de trace.
        rec.mode = "error"
        win.start_conversion()
        _check(_pump(app, lambda: win.state is m.UiState.IDLE), "erreur : état non rétabli")
        _check(errors and "Traceback" not in errors[-1] and "détail technique" not in errors[-1],
               "message d'erreur incorrect : " + str(errors))

        # Annulation.
        rec.mode = "block"
        win.start_conversion()
        _check(_pump(app, lambda: win.gauge.GetValue() >= 20), "progression non reçue")
        win.cancel()
        _check(_pump(app, lambda: win.state is m.UiState.IDLE), "annulation sans effet")
        _check("annulée" in win.status_text.GetValue(), "annulation non annoncée")

        # Export du texte.
        out_txt = Path(tmp) / "texte.txt"
        win.start_export(out_txt)
        _check(_pump(app, lambda: win.state is m.UiState.IDLE), "export non terminé")
        exported = out_txt.read_text(encoding="utf-8") if out_txt.is_file() else None
        _check(exported == "Texte extrait.", "export incorrect")
        _check("exporté" in win.status_text.GetValue(), "export non annoncé")

        # Fermeture pendant une conversion : confirmation puis annulation propre.
        win.start_conversion()
        _check(_pump(app, lambda: win.gauge.GetValue() >= 20), "progression non reçue (fermeture)")
        win.Close()
        _check(_pump(app, lambda: win.closed), "fenêtre non fermée après confirmation")
    app.Yield(True)

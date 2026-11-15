"""Fenêtre principale : contrôles natifs wx uniquement."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx
import wx.adv

from voxpage.gui import model as m
from voxpage.gui.deps import GuiDeps, default_deps
from voxpage.progress import Cancelled, CancelToken
from voxpage.tts.base import default_voice

try:  # Windows seulement
    import winsound
except ImportError:  # pragma: no cover
    winsound = None  # type: ignore[assignment]


class _Drop(wx.FileDropTarget):
    def __init__(self, callback: Callable[[list[str]], bool]) -> None:
        super().__init__()
        self._callback = callback

    def OnDropFiles(self, x: int, y: int, filenames: list[str]) -> bool:  # noqa: N802
        return self._callback(filenames)


class MainWindow(wx.Frame):
    def __init__(self, deps: GuiDeps | None = None) -> None:
        super().__init__(None, title="Voxpage — convertir un document en audio", style=wx.DEFAULT_FRAME_STYLE)
        self.deps = deps or default_deps()
        self.settings = self.deps.load_settings()
        self.closed = False
        self.state = m.UiState.IDLE
        self.result_files: list[Path] = []
        self.output_is_auto = True
        self.voices: list[Any] = []
        self.engine: Any = None
        self._worker: threading.Thread | None = None
        self._cancel: CancelToken | None = None
        self._closing = False
        self._playing = False
        self._play_gen = 0
        self._sound: Any = None
        self._temp_wav: str | None = None
        self._loading = True
        self.created: list[wx.Window] = []  # ordre de création = ordre de tabulation
        self.controls: dict[str, wx.Window] = {}
        self.static_labels: dict[str, wx.StaticText] = {}
        # Remplaçables (auto-test) : boîtes de dialogue.
        self.show_error: Callable[[str], None] = self._dialog_error
        self.confirm: Callable[[str, str], bool] = self._dialog_confirm
        self.ask_save_path: Callable[[str, str, str], str | None] = self._dialog_save

        self._build()
        self._load_voices()
        self._apply_settings()
        self._loading = False
        self._refresh_state()

        self.SetDropTarget(_Drop(self._on_drop))
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        self._bind_shortcuts()
        self.SetMinSize(self.FromDIP(wx.Size(560, 560)))
        self.SetSize(self.FromDIP(wx.Size(680, 640)))
        self.Centre()

    # ------------------------------------------------------------------ construction

    def _track(self, ctrl: wx.Window) -> wx.Window:
        self.created.append(ctrl)
        return ctrl

    def _label(self, key: str, text: str | None = None) -> wx.StaticText:
        st = wx.StaticText(self.panel, label=text or m.LABELS[key] + " :")
        self.static_labels[key] = st
        self._track(st)
        return st

    def _register(self, key: str, ctrl: wx.Window, name: str | None = None) -> wx.Window:
        ctrl.SetName(name or m.plain_label(m.LABELS[key]))
        self.controls[key] = ctrl
        self._track(ctrl)
        return ctrl

    def _button(self, key: str) -> wx.Button:
        b = wx.Button(self.panel, label=m.LABELS[key])
        self._register(key, b)
        return b

    def _build(self) -> None:
        self.panel = wx.Panel(self)
        gap = self.FromDIP(6)
        grid = wx.FlexGridSizer(3, gap, gap)
        grid.AddGrowableCol(1, 1)

        def row(label: wx.Window, ctrl: wx.Window, extra: wx.Window | None = None) -> None:
            grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            if extra is not None:
                grid.Add(extra, 0, wx.EXPAND)
            else:
                grid.AddSpacer(0)

        # Fichier d'entrée
        lab = self._label("input")
        self.input_text = wx.TextCtrl(self.panel)
        self._register("input", self.input_text)
        self.browse_btn = self._button("browse")
        row(lab, self.input_text, self.browse_btn)
        # Sortie
        lab = self._label("output")
        self.output_text = wx.TextCtrl(self.panel)
        self._register("output", self.output_text)
        self.output_btn = self._button("output_btn")
        row(lab, self.output_text, self.output_btn)
        # Voix, locuteur
        row(self._label("voice"), self._make_choice("voice"))
        row(self._label("speaker"), self._make_choice("speaker"))
        # Vitesse
        lab = self._label("speed", m.LABELS["speed"] + " : 1,0")
        self.speed_slider = wx.Slider(
            self.panel, value=10, minValue=m.SLIDER_MIN, maxValue=m.SLIDER_MAX, style=wx.SL_HORIZONTAL
        )
        self.speed_slider.SetPageSize(1)
        self._register("speed", self.speed_slider)
        row(lab, self.speed_slider)
        # Options
        for key, options in (("format", m.FORMATS), ("split", m.SPLITS), ("footnotes", m.FOOTNOTES),
                             ("ocr", m.OCR_MODES)):
            lab = self._label(key)
            c = wx.Choice(self.panel, choices=[label for _, label in options])
            self._register(key, c)
            row(lab, c)
        self.voice_choice = self.controls["voice"]
        self.speaker_choice = self.controls["speaker"]
        self.format_choice = self.controls["format"]
        self.split_choice = self.controls["split"]
        self.footnotes_choice = self.controls["footnotes"]
        self.ocr_choice = self.controls["ocr"]

        # Boutons d'action
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.preview_btn = self._button("preview")
        self.convert_btn = self._button("convert")
        self.cancel_btn = self._button("cancel")
        self.export_btn = self._button("export")
        self.open_btn = self._button("open_folder")
        for b in (self.preview_btn, self.convert_btn, self.cancel_btn, self.export_btn, self.open_btn):
            buttons.Add(b, 0, wx.RIGHT, gap)
        self.convert_btn.SetDefault()

        # Progression et état
        self.gauge = wx.Gauge(self.panel, range=100, style=wx.GA_HORIZONTAL)
        self.gauge.SetName("Progression")
        self._track(self.gauge)
        status_label = self._label("status")
        self.status_text = wx.TextCtrl(
            self.panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=self.FromDIP(wx.Size(-1, 110))
        )
        self._register("status", self.status_text)

        root = wx.BoxSizer(wx.VERTICAL)
        margin = self.FromDIP(12)
        root.Add(grid, 0, wx.EXPAND | wx.ALL, margin)
        root.Add(buttons, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, margin)
        root.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, margin)
        root.Add(status_label, 0, wx.LEFT | wx.RIGHT, margin)
        root.Add(self.status_text, 1, wx.EXPAND | wx.ALL, margin)
        self.panel.SetSizer(root)
        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(self.panel, 1, wx.EXPAND)
        self.SetSizer(frame_sizer)

        for key in ("browse", "output_btn", "preview", "convert", "cancel", "export", "open_folder"):
            self.controls[key].Bind(wx.EVT_BUTTON, getattr(self, f"_on_{key}"))
        self.input_text.Bind(wx.EVT_TEXT, self._on_input_text)
        self.output_text.Bind(wx.EVT_TEXT, self._on_output_text)
        self.voice_choice.Bind(wx.EVT_CHOICE, self._on_voice)
        self.speaker_choice.Bind(wx.EVT_CHOICE, self.on_setting_changed)
        self.speed_slider.Bind(wx.EVT_SLIDER, self._on_speed)
        for key in ("format", "split"):
            self.controls[key].Bind(wx.EVT_CHOICE, self._on_format_or_split)
        for key in ("footnotes", "ocr"):
            self.controls[key].Bind(wx.EVT_CHOICE, self.on_setting_changed)

    def _make_choice(self, key: str) -> wx.Choice:
        c = wx.Choice(self.panel)
        self._register(key, c)
        return c

    def _bind_shortcuts(self) -> None:
        ids = {name: wx.NewIdRef() for name in ("open", "convert", "cancel", "help")}
        self.Bind(wx.EVT_MENU, lambda e: self._on_browse(e), id=ids["open"])
        self.Bind(wx.EVT_MENU, lambda e: self._on_convert(e), id=ids["convert"])
        self.Bind(wx.EVT_MENU, lambda e: self._on_escape(e), id=ids["cancel"])
        self.Bind(wx.EVT_MENU, lambda e: self._on_help(e), id=ids["help"])
        entries = [
            (wx.ACCEL_CTRL, ord("O"), ids["open"]),
            (wx.ACCEL_CTRL, wx.WXK_RETURN, ids["convert"]),
            (wx.ACCEL_CTRL, wx.WXK_NUMPAD_ENTER, ids["convert"]),
            (wx.ACCEL_NORMAL, wx.WXK_ESCAPE, ids["cancel"]),
            (wx.ACCEL_NORMAL, wx.WXK_F1, ids["help"]),
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(entries))

    # ------------------------------------------------------------------ réglages

    def _load_voices(self) -> None:
        try:
            self.engine = self.deps.engine_factory()
            self.voices = list(self.engine.list_voices())
        except Exception as exc:  # noqa: BLE001 - affiché en français
            self.voices = []
            self._set_status("Aucune voix disponible : " + m.describe_error(exc), announce=False)
        self.voice_choice.Set([v.name for v in self.voices])
        if not self.voices:
            self._set_status("Aucune voix n'a été trouvée dans le dossier « voices ».", announce=False)

    def _apply_settings(self) -> None:
        s = self.settings
        idx = next((i for i, v in enumerate(self.voices) if v.id == s.voice_id), None)
        if idx is None:  # aucun réglage enregistré : voix française par défaut (pas la première)
            chosen = default_voice(self.voices, "fr")
            idx = self.voices.index(chosen) if chosen in self.voices else 0
        if self.voices:
            self.voice_choice.SetSelection(idx)
        self._fill_speakers()
        if 0 <= s.speaker < self.speaker_choice.GetCount():
            self.speaker_choice.SetSelection(s.speaker)
        self.speed_slider.SetValue(m.speed_to_slider(s.speed))
        self._update_speed_label()
        self._select(self.format_choice, m.FORMATS, s.audio.format)
        self._select(self.split_choice, m.SPLITS, s.audio.split)
        self._select(self.footnotes_choice, m.FOOTNOTES, s.extract.footnotes)
        self._select(self.ocr_choice, m.OCR_MODES, s.extract.ocr)

    @staticmethod
    def _select(choice: wx.Choice, options: tuple[tuple[str, str], ...], value: str) -> None:
        values = [v for v, _ in options]
        choice.SetSelection(values.index(value) if value in values else 0)

    @staticmethod
    def _value(choice: wx.Choice, options: tuple[tuple[str, str], ...]) -> str:
        return options[max(0, choice.GetSelection())][0]

    def _current_voice(self) -> Any | None:
        i = self.voice_choice.GetSelection()
        return self.voices[i] if 0 <= i < len(self.voices) else None

    def _fill_speakers(self) -> None:
        voice = self._current_voice()
        speakers = list(voice.speakers) if voice else []
        self.speaker_choice.Set(speakers)
        if speakers:
            self.speaker_choice.SetSelection(0)

    def _collect(self) -> Any:
        s = self.settings
        voice = self._current_voice()
        s.voice_id = voice.id if voice else s.voice_id
        s.speaker = max(0, self.speaker_choice.GetSelection())
        s.speed = m.slider_to_speed(self.speed_slider.GetValue())
        s.audio.format = self._value(self.format_choice, m.FORMATS)
        s.audio.split = self._value(self.split_choice, m.SPLITS)
        s.extract.footnotes = self._value(self.footnotes_choice, m.FOOTNOTES)
        s.extract.ocr = self._value(self.ocr_choice, m.OCR_MODES)
        return s

    def _save(self) -> None:
        if self._loading:
            return
        try:
            self.deps.save_settings(self._collect())
        except OSError:
            pass  # réglages non enregistrés : sans gravité pour la conversion

    def on_setting_changed(self, _evt: Any = None) -> None:
        self._save()

    def _update_speed_label(self) -> None:
        speed = m.slider_to_speed(self.speed_slider.GetValue())
        text = m.LABELS["speed"] + " : " + m.format_speed(speed)
        self.static_labels["speed"].SetLabel(text)
        self.speed_slider.SetName(m.speed_label(speed))
        self.panel.Layout()

    def _on_speed(self, evt: Any) -> None:
        self._update_speed_label()
        self._save()

    def _on_voice(self, evt: Any) -> None:
        self._fill_speakers()
        self._refresh_state()
        self._save()

    def _on_format_or_split(self, evt: Any) -> None:
        self._suggest_output()
        self._save()

    # ------------------------------------------------------------------ entrée / sortie

    def _input_path(self) -> Path | None:
        text = self.input_text.GetValue().strip().strip('"')
        return Path(text) if text else None

    def set_input(self, path: str | Path) -> None:
        self.input_text.SetValue(str(path))
        self.output_is_auto = True
        self._suggest_output()

    def _suggest_output(self) -> None:
        src = self._input_path()
        if src is None or not self.output_is_auto:
            return
        out = m.suggest_output(src, self._value(self.format_choice, m.FORMATS),
                               self._value(self.split_choice, m.SPLITS))
        self.output_text.ChangeValue(str(out))

    def _on_input_text(self, evt: Any) -> None:
        self._suggest_output()
        self._refresh_state()

    def _on_output_text(self, evt: Any) -> None:
        self.output_is_auto = False

    def _wildcard(self) -> str:
        return m.build_file_filter(self.deps.extensions())

    def _on_browse(self, evt: Any = None) -> None:
        if self.state is not m.UiState.IDLE:
            return
        with wx.FileDialog(self, "Choisir le document à convertir", wildcard=self._wildcard(),
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.set_input(dlg.GetPath())
                if self.convert_btn.IsEnabled():
                    self.convert_btn.SetFocus()

    def _on_output_btn(self, evt: Any) -> None:
        split = self._value(self.split_choice, m.SPLITS)
        current = Path(self.output_text.GetValue() or ".")
        if split == "chapters":
            with wx.DirDialog(self, "Choisir le dossier qui contiendra le dossier de sortie",
                              defaultPath=str(current.parent)) as dlg:
                if dlg.ShowModal() == wx.ID_OK and self._input_path():
                    out = m.suggest_output(self._input_path(), "", split, Path(dlg.GetPath()))
                    self.output_text.SetValue(str(out))
            return
        fmt = self._value(self.format_choice, m.FORMATS)
        with wx.FileDialog(self, "Enregistrer l'audio sous", defaultDir=str(current.parent),
                           defaultFile=current.name, wildcard=f"Fichier {fmt.upper()} (*.{fmt})|*.{fmt}",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.output_text.SetValue(dlg.GetPath())

    def _on_drop(self, filenames: list[str]) -> bool:
        if self.state is not m.UiState.IDLE or not filenames:
            return False
        self.set_input(filenames[0])
        self._set_status(f"Fichier choisi : {Path(filenames[0]).name}")
        return True

    # ------------------------------------------------------------------ dialogues

    def _dialog_error(self, text: str) -> None:
        wx.MessageBox(text, "Voxpage", wx.OK | wx.ICON_ERROR, self)

    def _dialog_confirm(self, title: str, text: str) -> bool:
        return wx.MessageBox(text, title, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) == wx.YES

    def _dialog_save(self, title: str, default_name: str, wildcard: str) -> str | None:
        with wx.FileDialog(self, title, defaultFile=default_name, wildcard=wildcard,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            return dlg.GetPath() if dlg.ShowModal() == wx.ID_OK else None

    def _on_help(self, evt: Any = None) -> None:
        style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        with wx.Dialog(self, title="Aide de Voxpage", style=style) as dlg:
            text = wx.TextCtrl(dlg, value=m.SHORTCUTS_HELP, style=wx.TE_MULTILINE | wx.TE_READONLY,
                               size=dlg.FromDIP(wx.Size(460, 280)))
            text.SetName("Aide")
            ok = wx.Button(dlg, wx.ID_OK, "Fermer")
            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(text, 1, wx.EXPAND | wx.ALL, dlg.FromDIP(10))
            sizer.Add(ok, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, dlg.FromDIP(10))
            dlg.SetSizerAndFit(sizer)
            ok.SetDefault()
            text.SetFocus()
            dlg.ShowModal()

    # ------------------------------------------------------------------ état

    def _refresh_state(self) -> None:
        if self._loading:
            return
        voice = self._current_voice()
        src = self._input_path()
        flags = m.ui_flags(
            self.state,
            has_input=bool(src),
            has_voice=voice is not None,
            multi_speaker=bool(voice and len(voice.speakers) > 1),
            has_result=bool(self.result_files),
            playing=self._playing,
        )
        for key, ctrl in self.controls.items():
            if key in flags:
                ctrl.Enable(flags[key])

    def _set_state(self, state: m.UiState) -> None:
        self.state = state
        self._refresh_state()

    def _set_status(self, text: str, announce: bool = True) -> None:
        self.status_text.ChangeValue(text)
        if announce:
            self._notify(self.status_text)

    def _notify(self, ctrl: wx.Window) -> None:
        """Alerte accessible (MSAA) pour que le lecteur d'écran lise la ligne d'état sans prendre le focus."""
        try:
            event = getattr(wx, "ACC_EVENT_SYSTEM_ALERT", 0x0002)
            wx.Accessible.NotifyEvent(event, ctrl, getattr(wx, "OBJID_CLIENT", -4), 0)
        except Exception:  # noqa: BLE001 - indisponible hors Windows : le focus sert de repli
            pass

    def _beep(self) -> None:
        try:
            if winsound is not None:
                winsound.MessageBeep()
            else:
                wx.Bell()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ tâche de fond

    def _validate_input(self) -> Path | None:
        src = self._input_path()
        if src is None or not src.is_file():
            self.show_error("Le fichier à convertir est introuvable. Choisissez-le avec « Parcourir ».")
            self.input_text.SetFocus()
            return None
        exts = [e.lower() for e in self.deps.extensions()]
        if src.suffix.lower() not in exts:
            self.show_error(
                f"Ce format n'est pas pris en charge : « {src.suffix or src.name} ». "
                f"Formats acceptés : {', '.join(exts)}."
            )
            self.input_text.SetFocus()
            return None
        return src

    def _spawn(self, kind: str, start_message: str, work: Callable[[Callable, CancelToken], Any]) -> None:
        cancel = CancelToken()
        throttle = m.ProgressThrottle()
        self._cancel = cancel
        self.result_files = []
        self.gauge.SetValue(0)
        self._set_state(m.UiState.CONVERTING if kind == "convert" else m.UiState.EXPORTING)
        self._set_status(start_message)
        self.cancel_btn.SetFocus()

        def progress(step: str, fraction: float) -> None:
            u = throttle.feed(step, fraction)
            if u.percent_changed or u.message:
                wx.CallAfter(self._on_progress, u)

        def run() -> None:
            try:
                outcome: tuple[str, Any] = ("ok", work(progress, cancel))
            except Cancelled:
                outcome = ("cancelled", None)
            except BaseException as exc:  # noqa: BLE001 - tout est rapporté à l'utilisateur
                outcome = ("error", exc)
            wx.CallAfter(self._on_done, kind, outcome)

        self._worker = threading.Thread(target=run, name=f"voxpage-{kind}", daemon=True)
        self._worker.start()

    def _on_progress(self, u: m.Update) -> None:
        if self.closed:
            return
        if u.percent_changed:
            self.gauge.SetValue(u.percent)
        if u.message:
            self._set_status(u.message)

    def start_conversion(self) -> None:
        src = self._validate_input()
        if src is None:
            return
        out_text = self.output_text.GetValue().strip()
        if not out_text:
            self.show_error("Indiquez le fichier de sortie avec « Choisir la sortie ».")
            self.output_text.SetFocus()
            return
        out = Path(out_text)
        if out.exists() and not self.confirm("Voxpage", f"« {out.name} » existe déjà. Le remplacer ?"):
            return
        if self._playing:
            self._stop_playback()
        settings = self._collect()
        self._save()
        convert = self.deps.convert
        self._spawn(
            "convert",
            "Conversion en cours. Appuyez sur Échap pour annuler.",
            lambda progress, cancel: convert(src, out, settings, progress=progress, cancel=cancel),
        )

    def start_export(self, target: Path) -> None:
        src = self._validate_input()
        if src is None:
            return
        settings = self._collect()
        extract_text = self.deps.extract_text

        def work(progress: Callable, cancel: CancelToken) -> Path:
            text = extract_text(src, settings, progress=progress, cancel=cancel)
            cancel.raise_if_cancelled()
            target.write_text(text, encoding="utf-8")
            return target

        self._spawn("export", "Extraction du texte en cours. Appuyez sur Échap pour annuler.", work)

    def _on_convert(self, evt: Any = None) -> None:
        if self.state is m.UiState.IDLE and self.convert_btn.IsEnabled():
            self.start_conversion()

    def _on_export(self, evt: Any = None) -> None:
        if self.state is not m.UiState.IDLE:
            return
        src = self._input_path()
        name = (src.stem if src else "texte") + ".txt"
        path = self.ask_save_path("Exporter le texte", name, "Texte (*.txt)|*.txt")
        if path:
            self.start_export(Path(path))

    def cancel(self) -> None:
        if self._cancel and self._worker and self._worker.is_alive():
            self._cancel.cancel()
            self._set_status("Annulation en cours…")

    def _on_cancel(self, evt: Any = None) -> None:
        self.cancel()

    def _on_escape(self, evt: Any = None) -> None:
        if self.state in (m.UiState.CONVERTING, m.UiState.EXPORTING):
            self.cancel()

    def _on_done(self, kind: str, outcome: tuple[str, Any]) -> None:
        self._worker = None
        if self.closed:
            return
        status, payload = outcome
        self.gauge.SetValue(100 if status == "ok" else self.gauge.GetValue())
        self._set_state(m.UiState.IDLE)
        if self._closing:
            self.closed = True
            self.Destroy()
            return
        if status == "ok":
            if kind == "convert":
                self.result_files = list(payload.files)
                text = m.result_message(self.result_files, payload.duration_s, list(payload.warnings))
            else:
                text = f"Texte exporté dans : {payload}"
            self._refresh_state()
            self._set_status(text)
            self._beep()
            self.status_text.SetFocus()
        elif status == "cancelled":
            self._set_status("Opération annulée.")
            self.convert_btn.SetFocus()
        else:
            message = m.describe_error(payload)
            self._set_status("Échec : " + message)
            self._beep()
            self.show_error(message)
            self.status_text.SetFocus()

    def _on_open_folder(self, evt: Any = None) -> None:
        if not self.result_files:
            return
        folder = self.result_files[0].parent
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603,S607
        except OSError:
            self.show_error(f"Impossible d'ouvrir le dossier « {folder} ».")

    # ------------------------------------------------------------------ extrait sonore

    def _on_preview(self, evt: Any = None) -> None:
        if self._playing:
            self._stop_playback()
            return
        voice = self._current_voice()
        if voice is None or self.state is not m.UiState.IDLE:
            return
        speaker = max(0, self.speaker_choice.GetSelection())
        speed = m.slider_to_speed(self.speed_slider.GetValue())
        engine = self.engine
        self._set_state(m.UiState.SYNTH)
        self._set_status("Préparation de l'extrait…")

        def run() -> None:
            try:
                samples, rate = engine.synthesize(m.sample_sentence(voice.lang), voice.id, speaker, speed)
                fd, path = tempfile.mkstemp(suffix=".wav", prefix="voxpage-")
                os.close(fd)
                with wave.open(path, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(int(rate))
                    w.writeframes(samples.astype("<i2").tobytes())
                wx.CallAfter(self._play, path, len(samples) / float(rate))
            except BaseException as exc:  # noqa: BLE001
                wx.CallAfter(self._preview_failed, exc)

        threading.Thread(target=run, name="voxpage-preview", daemon=True).start()

    def _preview_failed(self, exc: BaseException) -> None:
        if self.closed:
            return
        self._set_state(m.UiState.IDLE)
        self._set_status("Échec de l'extrait : " + m.describe_error(exc))
        self.show_error(m.describe_error(exc))
        self.preview_btn.SetFocus()

    def _play(self, path: str, seconds: float) -> None:
        if self.closed:
            self._remove_temp(path)
            return
        self._remove_temp()
        self._temp_wav = path
        self._play_gen += 1
        gen = self._play_gen
        try:
            if winsound is not None:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                self._sound = wx.adv.Sound(path)
                self._sound.Play(wx.adv.SOUND_ASYNC)
        except Exception as exc:  # noqa: BLE001
            self._preview_failed(exc)
            return
        self._playing = True
        self._set_state(m.UiState.IDLE)
        self._relabel_preview(playing=True)
        self._set_status("Lecture de l'extrait.", announce=False)
        wx.CallLater(int(seconds * 1000) + 400, self._on_play_end, gen)

    def _relabel_preview(self, playing: bool) -> None:
        label = "Arrêter l'extrait" if playing else m.LABELS["preview"]
        self.preview_btn.SetLabel(label)
        self.preview_btn.SetName(m.plain_label(label))

    def _on_play_end(self, gen: int) -> None:
        if not self.closed and gen == self._play_gen and self._playing:
            self._stop_playback()

    def _stop_playback(self) -> None:
        self._play_gen += 1
        try:
            if winsound is not None:
                winsound.PlaySound(None, winsound.SND_PURGE)
            if self._sound is not None:
                self._sound.Stop()
        except Exception:  # noqa: BLE001
            pass
        self._sound = None
        self._playing = False
        self._remove_temp()
        if not self.closed:
            self._relabel_preview(playing=False)
            self._refresh_state()
            self._set_status("Extrait terminé.", announce=False)

    def _remove_temp(self, path: str | None = None) -> None:
        target = path or self._temp_wav
        if target:
            try:
                os.remove(target)
            except OSError:
                pass
            if target == self._temp_wav:
                self._temp_wav = None

    # ------------------------------------------------------------------ fermeture

    def _on_close(self, evt: wx.CloseEvent) -> None:
        if self._worker and self._worker.is_alive():
            if not self.confirm("Voxpage", "Une opération est en cours. L'annuler et quitter ?"):
                evt.Veto()
                return
            self._closing = True
            self.cancel()
            evt.Veto()  # la fenêtre se ferme quand le thread a terminé (_on_done)
            return
        self._stop_playback()
        evt.Skip()

    def _on_destroy(self, evt: Any) -> None:
        if evt.GetEventObject() is self:
            self.closed = True
            self._remove_temp()
        evt.Skip()


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
    except Exception:  # noqa: BLE001 - déjà défini par le manifeste, ou Windows ancien
        pass


def run_app(deps: GuiDeps | None = None) -> int:
    _enable_dpi_awareness()
    app = wx.App(False)
    win = MainWindow(deps)
    win.Show()
    win.input_text.SetFocus()
    app.MainLoop()
    return 0

"""Dialogue « Prononciations » : contrôles natifs wx, tout au clavier (logique dans pronunciations.py)."""

from __future__ import annotations

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
from voxpage.gui import pronunciations as p
from voxpage.normalize.lexicon import LexiconError

try:  # Windows seulement
    import winsound
except ImportError:  # pragma: no cover
    winsound = None  # type: ignore[assignment]


class PronunciationDialog(wx.Dialog):
    """`synthesize(texte) -> (échantillons, fréquence)` : voix courante de la fenêtre (None : pas de voix)."""

    def __init__(
        self,
        parent: wx.Window | None,
        path: Path,
        synthesize: Callable[[str], tuple[Any, int]] | None = None,
        voice_lang: str = "fr",
    ) -> None:
        super().__init__(parent, title="Prononciations", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.model = p.PronunciationModel(path)
        self.synthesize = synthesize
        self.voice_lang = voice_lang
        self.created: list[wx.Window] = []
        self.controls: dict[str, wx.Window] = {}
        self.static_labels: dict[str, wx.StaticText] = {}
        self._lines: list[int] = []  # numéro de ligne du fichier de chaque ligne de la liste
        self._temp: str | None = None
        self._sound: Any = None
        self._busy = False
        # Remplaçables (auto-test) : boîtes de dialogue.
        self.show_error: Callable[[str], None] = self._dialog_error
        self.confirm: Callable[[str, str], bool] = lambda title, text: (
            wx.MessageBox(text, title, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) == wx.YES
        )
        self.open_editor: Callable[[Path], None] = self._open_in_editor
        self._build()
        self.refresh()
        self.Bind(wx.EVT_ACTIVATE, self._on_activate)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        self.SetMinSize(self.FromDIP(wx.Size(520, 520)))
        self.SetSize(self.FromDIP(wx.Size(640, 600)))
        self.CentreOnParent()

    def _dialog_error(self, text: str) -> None:
        wx.MessageBox(text, "Voxpage", wx.OK | wx.ICON_ERROR, self)

    # ------------------------------------------------------------------ construction

    def _label(self, key: str) -> wx.StaticText:
        st = wx.StaticText(self, label=p.LABELS[key] + " :")
        self.static_labels[key] = st
        self.created.append(st)
        return st

    def _register(self, key: str, ctrl: wx.Window) -> wx.Window:
        ctrl.SetName(m.plain_label(p.LABELS[key]))
        self.controls[key] = ctrl
        self.created.append(ctrl)
        return ctrl

    def _button(self, key: str, id_: int = wx.ID_ANY) -> wx.Button:
        b = wx.Button(self, id_, label=p.LABELS[key])
        self._register(key, b)
        return b

    def _build(self) -> None:
        gap = self.FromDIP(6)
        margin = self.FromDIP(12)
        root = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(self, label=p.HELP)
        intro.Wrap(self.FromDIP(560))
        root.Add(intro, 0, wx.ALL, margin)

        root.Add(self._label("pron_list"), 0, wx.LEFT | wx.RIGHT, margin)
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.list.InsertColumn(0, "Écrit", width=self.FromDIP(170))
        self.list.InsertColumn(1, "Dit", width=self.FromDIP(250))
        self.list.InsertColumn(2, "Langue", width=self.FromDIP(100))
        self._register("pron_list", self.list)
        root.Add(self.list, 1, wx.EXPAND | wx.ALL, margin)

        grid = wx.FlexGridSizer(2, gap, gap)
        grid.AddGrowableCol(1, 1)
        for key in ("pron_written", "pron_spoken"):
            grid.Add(self._label(key), 0, wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.TextCtrl(self)
            self._register(key, ctrl)
            grid.Add(ctrl, 1, wx.EXPAND)
        grid.Add(self._label("pron_lang"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.lang_choice = wx.Choice(self, choices=[label for _, label in p.LANG_CHOICES])
        self.lang_choice.SetSelection(0)
        self._register("pron_lang", self.lang_choice)
        grid.Add(self.lang_choice, 1, wx.EXPAND)
        root.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, margin)
        self.written_text = self.controls["pron_written"]
        self.spoken_text = self.controls["pron_spoken"]

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.add_btn = self._button("pron_add")
        self.modify_btn = self._button("pron_modify")
        self.delete_btn = self._button("pron_delete")
        self.listen_btn = self._button("pron_listen")
        self.listen_raw_btn = self._button("pron_listen_raw")
        for b in (self.add_btn, self.modify_btn, self.delete_btn, self.listen_btn, self.listen_raw_btn):
            row.Add(b, 0, wx.RIGHT, gap)
        root.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, margin)
        self.add_btn.SetDefault()

        root.Add(self._label("pron_status"), 0, wx.LEFT | wx.RIGHT, margin)
        self.status_text = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=self.FromDIP(wx.Size(-1, 70))
        )
        self._register("pron_status", self.status_text)
        root.Add(self.status_text, 0, wx.EXPAND | wx.ALL, margin)

        bottom = wx.BoxSizer(wx.HORIZONTAL)
        self.open_btn = self._button("pron_open")
        self.close_btn = self._button("pron_close", wx.ID_CANCEL)  # Échap = bouton d'identifiant ID_CANCEL
        bottom.Add(self.open_btn, 0, wx.RIGHT, gap)
        bottom.AddStretchSpacer(1)
        bottom.Add(self.close_btn, 0)
        root.Add(bottom, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, margin)
        self.SetSizer(root)

        self.add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        self.modify_btn.Bind(wx.EVT_BUTTON, self._on_modify)
        self.delete_btn.Bind(wx.EVT_BUTTON, self._on_delete)
        self.listen_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_listen(True))
        self.listen_raw_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_listen(False))
        self.open_btn.Bind(wx.EVT_BUTTON, self._on_open)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_select)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, lambda e: self._refresh_buttons())
        self.list.Bind(wx.EVT_LIST_KEY_DOWN, self._on_list_key)
        self.written_text.Bind(wx.EVT_TEXT, lambda e: self._refresh_buttons())
        self.spoken_text.Bind(wx.EVT_TEXT, lambda e: self._refresh_buttons())

    # ------------------------------------------------------------------ état

    def say(self, text: str, announce: bool = True) -> None:
        self.status_text.ChangeValue(text)
        if announce:
            try:
                event = getattr(wx, "ACC_EVENT_SYSTEM_ALERT", 0x0002)
                wx.Accessible.NotifyEvent(event, self.status_text, getattr(wx, "OBJID_CLIENT", -4), 0)
            except Exception:  # noqa: BLE001 - indisponible hors Windows
                pass

    def selected_line(self) -> int | None:
        i = self.list.GetFirstSelected()
        return self._lines[i] if 0 <= i < len(self._lines) else None

    def refresh(self, select_line: int | None = None) -> None:
        self.list.DeleteAllItems()
        self._lines = []
        for r in self.model.rows():
            i = self.list.InsertItem(self.list.GetItemCount(), r.written)
            self.list.SetItem(i, 1, r.spoken_display)
            self.list.SetItem(i, 2, r.lang_name)
            self._lines.append(r.line)
        if select_line in self._lines:
            i = self._lines.index(select_line)
            self.list.Select(i)
            self.list.Focus(i)
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        has_text = bool(self.written_text.GetValue().strip())
        selected = self.selected_line() is not None
        voice = self.synthesize is not None and not self._busy
        self.add_btn.Enable(has_text)
        self.modify_btn.Enable(has_text and selected)
        self.delete_btn.Enable(selected)
        self.listen_btn.Enable(voice and bool(self.spoken_text.GetValue().strip()))
        self.listen_raw_btn.Enable(voice and has_text)

    def _lang(self) -> str:
        return p.LANG_CHOICES[max(0, self.lang_choice.GetSelection())][0]

    def _fields(self) -> tuple[str, str, str]:
        return self.written_text.GetValue().strip(), self.spoken_text.GetValue().strip(), self._lang()

    def _on_select(self, evt: Any) -> None:
        line = self.selected_line()
        row = self.model.row_at(line) if line else None
        if row:
            self.written_text.ChangeValue(row.written)
            self.spoken_text.ChangeValue(row.spoken)
            self.lang_choice.SetSelection([c for c, _ in p.LANG_CHOICES].index(row.lang))
        self._refresh_buttons()

    # ------------------------------------------------------------------ actions

    def _run(self, action: Callable[[], str], focus: wx.Window | None = None) -> bool:
        try:
            message = action()
        except LexiconError as exc:
            self.say(str(exc))
            self.show_error(str(exc))
            return False
        except OSError as exc:
            text = m.describe_error(exc)
            self.say("Échec : " + text)
            self.show_error(text)
            return False
        self.say(message + " " + self.model.summary())
        if focus is not None:
            focus.SetFocus()
        return True

    def _on_add(self, evt: Any = None) -> None:
        written, spoken, lang = self._fields()
        if self._run(lambda: self.model.add(written, spoken, lang)):
            self.refresh()
            self.written_text.ChangeValue("")
            self.spoken_text.ChangeValue("")
            self._refresh_buttons()
            self.written_text.SetFocus()

    def _on_modify(self, evt: Any = None) -> None:
        line = self.selected_line()
        if line is None:
            return
        written, spoken, lang = self._fields()
        if self._run(lambda: self.model.update(line, written, spoken, lang)):
            self.refresh(line)
            self.list.SetFocus()

    def _on_delete(self, evt: Any = None) -> None:
        line = self.selected_line()
        row = self.model.row_at(line) if line else None
        if row is None:
            return
        if not self.confirm("Voxpage", self.model.confirm_delete_text(row)):
            return
        index = self.list.GetFirstSelected()
        if self._run(lambda: self.model.remove(line)):
            self.refresh()
            count = self.list.GetItemCount()
            if count:
                self.list.Select(min(index, count - 1))
                self.list.Focus(min(index, count - 1))
                self.list.SetFocus()
            else:
                self.written_text.SetFocus()

    def _on_list_key(self, evt: wx.ListEvent) -> None:
        if evt.GetKeyCode() == wx.WXK_DELETE:
            self._on_delete()
        else:
            evt.Skip()

    def _on_open(self, evt: Any = None) -> None:
        try:
            path = self.model.ensure_file()
            self.open_editor(path)
        except OSError as exc:
            self.show_error(m.describe_error(exc))
            return
        self.say("Fichier ouvert dans l'éditeur de texte. Enregistrez-le puis revenez dans cette fenêtre : "
                 "la liste sera mise à jour.")

    @staticmethod
    def _open_in_editor(path: Path) -> None:
        if sys.platform == "win32":
            subprocess.Popen(["notepad.exe", str(path)])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607

    def _on_activate(self, evt: Any) -> None:
        if evt.GetActive() and self.model.changed_on_disk():
            keep = self.selected_line()
            self.model.reload()
            self.refresh(keep)
            self.say("Le fichier a été modifié : liste mise à jour. " + self.model.summary())
        evt.Skip()

    # ------------------------------------------------------------------ écoute

    def _on_listen(self, with_dictionary: bool) -> None:
        if self.synthesize is None or self._busy:
            return
        written, spoken, _ = self._fields()
        lang = self._lang() or self.voice_lang
        text = self.model.listen_text(written, spoken, with_dictionary, lang)
        if not text:
            return
        self._busy = True
        self._refresh_buttons()
        self.say("Préparation de l'écoute…", announce=False)
        synthesize = self.synthesize

        def run() -> None:
            try:
                samples, rate = synthesize(text)
                fd, path = tempfile.mkstemp(suffix=".wav", prefix="voxpage-")
                os.close(fd)
                with wave.open(path, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(int(rate))
                    w.writeframes(samples.astype("<i2").tobytes())
                wx.CallAfter(self._play, path, len(samples) / float(rate), with_dictionary, text)
            except BaseException as exc:  # noqa: BLE001
                wx.CallAfter(self._listen_failed, exc)

        threading.Thread(target=run, name="voxpage-pron", daemon=True).start()

    def _listen_failed(self, exc: BaseException) -> None:
        self._busy = False
        if not self:
            return
        self._refresh_buttons()
        text = m.describe_error(exc)
        self.say("Échec de l'écoute : " + text)
        self.show_error(text)

    def _play(self, path: str, seconds: float, with_dictionary: bool, text: str) -> None:
        self._busy = False
        if not self:
            self._remove(path)
            return
        self._remove()
        self._temp = path
        try:
            if winsound is not None:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                self._sound = wx.adv.Sound(path)
                self._sound.Play(wx.adv.SOUND_ASYNC)
        except Exception as exc:  # noqa: BLE001
            self._listen_failed(exc)
            return
        self._refresh_buttons()
        what = "Avec le dictionnaire" if with_dictionary else "Sans le dictionnaire"
        self.say(f"{what} : lecture de « {text} ».", announce=False)

    def _remove(self, path: str | None = None) -> None:
        target = path or self._temp
        if not target:
            return
        try:
            if winsound is not None:
                winsound.PlaySound(None, winsound.SND_PURGE)
            if self._sound is not None:
                self._sound.Stop()
            os.remove(target)
        except Exception:  # noqa: BLE001
            pass
        self._sound = None
        if target == self._temp:
            self._temp = None

    def _on_destroy(self, evt: Any) -> None:
        if evt.GetEventObject() is self:
            self._remove()
        evt.Skip()

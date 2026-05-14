# ai_radio_dialog.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Adw, GObject, Gtk

import logging
logger = logging.getLogger(__name__)


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/ai_radio_dialog.ui")
class HTAIRadioDialog(Adw.Dialog):
    __gtype_name__ = "HTAIRadioDialog"

    __gsignals__ = {
        "generate": (GObject.SignalFlags.RUN_FIRST, None, (str, bool))
    }

    prompt_entry = Gtk.Template.Child()
    use_playlists_check = Gtk.Template.Child()
    spinner = Gtk.Template.Child()
    generate_button = Gtk.Template.Child()
    cancel_gen_button = Gtk.Template.Child()

    def __init__(self) -> None:
        super().__init__()
        self.prompt_entry.connect("changed", self._on_text_changed)
        self.cancel_gen_button.connect("clicked", self._on_cancel_clicked)
        self.connect("map", lambda *_: self.prompt_entry.grab_focus())

    def _on_text_changed(self, *args) -> None:
        has_text = len(self.prompt_entry.get_text().strip()) > 0
        self.generate_button.set_sensitive(has_text)

    @Gtk.Template.Callback("on_generate_button_clicked")
    def _on_generate_clicked(self, *args) -> None:
        prompt = self.prompt_entry.get_text().strip()
        use_playlists = self.use_playlists_check.get_active()
        self._set_generating(True)
        self.emit("generate", prompt, use_playlists)

    def _on_cancel_clicked(self, *args) -> None:
        self.close()

    def _set_generating(self, generating: bool) -> None:
        self.prompt_entry.set_sensitive(not generating)
        self.use_playlists_check.set_sensitive(not generating)
        self.generate_button.set_visible(not generating)
        self.spinner.set_visible(generating)
        self.cancel_gen_button.set_visible(generating)

    def reset(self) -> None:
        self._set_generating(False)

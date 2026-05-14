# ai_radio_page.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

import threading
import logging
from gettext import gettext as _

from gi.repository import GLib, GObject, Gtk

from .track_list_page import TrackListPage
from ..lib import utils

logger = logging.getLogger(__name__)


class HTAIRadioPage(TrackListPage):
    """Result page for AI-generated radio stations."""

    __gtype_name__ = "HTAIRadioPage"

    __gsignals__ = {
        "refine": (GObject.SignalFlags.RUN_FIRST, None, (str, GObject.TYPE_PYOBJECT))
    }

    def __init__(
        self,
        prompt: str,
        title: str,
        tracks: list,
        suggestions: list,
        conversation_history: list,
    ) -> None:
        super().__init__()
        self._prompt = prompt
        self._ai_title = title
        self._tracks = tracks
        self._suggestions = suggestions
        self._history = conversation_history
        self._chips_box: Gtk.Box | None = None
        self._refine_entry: Gtk.Entry | None = None
        self._save_button: Gtk.Button | None = None
        self._loaded = False
        self._pending_update: tuple | None = None
        # Add bottom bar before the page is pushed to the navigation view.
        # Calling add_bottom_bar() after the ToolbarView is rendered causes a
        # continuous layout loop that corrupts GTK's internal state.
        self.object.add_bottom_bar(self._build_bottom_bar())

    def _load_async(self) -> None:
        pass

    def _load_finish(self) -> None:
        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/tracks_list_template.ui"
        )
        main_box = builder.get_object("_main")

        self.original_tracks = list(self._tracks)

        self._setup_ui(
            builder,
            self._ai_title,
            self._prompt,
            self._tracks,
            hide_share=True,
        )

        # Insert suggestion chips between the separator and the auto_load widget
        self._chips_box = Gtk.Box(spacing=6, orientation=Gtk.Orientation.HORIZONTAL)
        chips_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
            margin_start=12,
            margin_end=12,
            margin_top=6,
            margin_bottom=6,
        )
        chips_scroll.set_child(self._chips_box)
        self._populate_chips(self._suggestions)

        sep = self._find_separator(main_box)
        sibling = sep if sep else self.auto_load
        main_box.insert_child_after(chips_scroll, sibling)

        self._loaded = True
        if self._pending_update:
            self.update_tracks(*self._pending_update)
            self._pending_update = None


    # ------------------------------------------------------------------
    # Suggestion chips

    def _find_separator(self, box: Gtk.Box) -> Gtk.Widget | None:
        child = box.get_first_child()
        while child:
            if isinstance(child, Gtk.Separator):
                return child
            child = child.get_next_sibling()
        return None

    def _populate_chips(self, suggestions: list) -> None:
        while self._chips_box.get_first_child():
            self._chips_box.remove(self._chips_box.get_first_child())
        for suggestion in suggestions:
            chip = Gtk.Button(label=suggestion, css_classes=["pill"])
            chip.connect("clicked", self._on_chip_clicked, suggestion)
            self._chips_box.append(chip)

    def _on_chip_clicked(self, btn, suggestion: str) -> None:
        self._refine_entry.set_text(suggestion)
        self._on_refine_submit()

    # ------------------------------------------------------------------
    # Bottom bar: refinement entry + save button

    def _build_bottom_bar(self) -> Gtk.ActionBar:
        bar = Gtk.ActionBar()

        self._refine_entry = Gtk.Entry(
            placeholder_text=_("Refine: make it more upbeat…"),
            hexpand=True,
            margin_start=6,
            margin_end=6,
        )

        refine_btn = Gtk.Button(
            icon_name="go-next-symbolic",
            sensitive=False,
            valign=Gtk.Align.CENTER,
            css_classes=["flat", "circular"],
        )
        self.signals.append((refine_btn, refine_btn.connect(
            "clicked", lambda *_: self._on_refine_submit()
        )))
        self.signals.append((self._refine_entry, self._refine_entry.connect(
            "notify::text",
            lambda *_: refine_btn.set_sensitive(
                len(self._refine_entry.get_text().strip()) > 0
            ),
        )))
        self.signals.append((self._refine_entry, self._refine_entry.connect(
            "activate", lambda *_: self._on_refine_submit()
        )))

        center_box = Gtk.Box(spacing=6, hexpand=True)
        center_box.append(self._refine_entry)
        center_box.append(refine_btn)
        bar.set_center_widget(center_box)

        self._save_button = Gtk.Button(
            label=_("Save"),
            valign=Gtk.Align.CENTER,
            css_classes=["suggested-action", "pill"],
            margin_start=6,
        )
        self.signals.append((self._save_button, self._save_button.connect(
            "clicked", self._on_save_clicked
        )))
        bar.pack_end(self._save_button)

        return bar

    def _on_refine_submit(self) -> None:
        text = self._refine_entry.get_text().strip()
        if not text:
            return
        self.emit("refine", text, self._history)

    # ------------------------------------------------------------------
    # Save as playlist

    def _on_save_clicked(self, *args) -> None:
        self._save_button.set_sensitive(False)
        spinner = Gtk.Spinner(spinning=True)
        self._save_button.set_child(spinner)
        threading.Thread(target=self._th_save_as_playlist).start()

    def _th_save_as_playlist(self) -> None:
        total = len(self._tracks)
        success_count = 0
        try:
            playlist = utils.session.user.create_playlist(
                self._ai_title, _("Generated by AI Radio")
            )
            for track in self._tracks:
                try:
                    playlist.add([track.id])
                    success_count += 1
                except Exception:
                    logger.exception("Failed to add track %s to playlist", track.id)
        except Exception:
            logger.exception("Failed to create AI Radio playlist")
            GLib.idle_add(self._on_save_complete, 0, total)
            return
        GLib.idle_add(self._on_save_complete, success_count, total)

    def _on_save_complete(self, success_count: int, total: int) -> None:
        self._save_button.set_sensitive(True)
        self._save_button.set_child(None)
        self._save_button.set_label(_("Save"))
        if success_count == total and total > 0:
            utils.send_toast(_("Saved as playlist"), 3)
        elif success_count > 0:
            utils.send_toast(
                _("Saved playlist with {} of {} tracks").format(success_count, total), 4
            )
        else:
            utils.send_toast(_("Could not save playlist — try again"), 3)

    # ------------------------------------------------------------------
    # Public API for window.py

    def update_tracks(
        self,
        title: str,
        tracks: list,
        suggestions: list,
        history: list,
    ) -> None:
        if not self._loaded:
            self._pending_update = (title, tracks, suggestions, history)
            return

        self._ai_title = title
        self._tracks = tracks
        self._history = history
        self.original_tracks = list(tracks)

        self._populate_chips(suggestions)
        self.auto_load.set_items(tracks)
        self.auto_load.set_function(None)
        if self._refine_entry:
            self._refine_entry.set_text("")

    # ------------------------------------------------------------------
    # Override play / shuffle to use the tracks list directly

    def on_play_button_clicked(self, btn) -> None:
        utils.player_object.play_this(self._tracks)

    def on_shuffle_button_clicked(self, btn) -> None:
        utils.player_object.shuffle_this(self._tracks)

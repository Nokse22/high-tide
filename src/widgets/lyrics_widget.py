# lyrics_widget.py
#
# Copyright 2025 Nokse <nokse@posteo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from gi.repository import Adw, Gio, GObject, Gtk

from ..disconnectable_iface import IDisconnectable


class HTLine(GObject.Object):
    def __init__(self, text="", time=None):
        super().__init__()
        self.text = text
        self.time = time


class LineItemFactory(Gtk.SignalListItemFactory):
    def __init__(self):
        super().__init__()
        self.connect("setup", self._on_setup)
        self.connect("bind", self._on_bind)

    def _on_setup(self, factory, list_item):
        label = Gtk.Label(
            xalign=0.0,
            halign=Gtk.Align.FILL,
            hexpand=True,
            valign=Gtk.Align.FILL,
            vexpand=True,
            wrap=True,
            margin_start=12,
            margin_top=3,
            margin_bottom=3,
            margin_end=12,
        )

        list_item.set_child(label)

    def _on_bind(self, factory, list_item):
        label = list_item.get_child()
        lyric_line = list_item.get_item()

        if lyric_line.text:
            label.set_text(lyric_line.text)
        else:
            label.set_text("...")


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/widgets/lyrics_widget.ui")
class HTLyricsWidget(Gtk.Box, IDisconnectable):
    """A widget to display a track lyrics"""

    __gtype_name__ = "HTLyricsWidget"

    __gsignals__ = {"seek": (GObject.SignalFlags.RUN_FIRST, None, (int,))}

    list_view = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    sync_button = Gtk.Template.Child()

    has_timestamps = False

    def __init__(self, _item=None):
        IDisconnectable.__init__(self)
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        self.list_store = Gio.ListStore.new(HTLine)
        self.factory = LineItemFactory()
        self.selection_model = None
        self.handler_id = None

        self.list_view.set_factory(self.factory)

        self.adjustment = self.list_view.get_vadjustment()
        self.adjustment.connect("value-changed", self._on_scroll)

        self.sync_button.connect("clicked", self._on_sync_button_click)
        
        self.prev_index = 0
        self.prev_value = 0

    def set_lyrics(self, lyrics_text: str):
        """Set the lyrics.

        Args:
            lyrics_text (str): The lyrics (may or may not contain timestamps).
        """
        self.stack.set_visible_child_name("lyrics_page")
        self.list_store.remove_all()
        self.autoscroll_enabled = True
        self.scroll_error_count = 0

        lines = lyrics_text.splitlines()
        timestamp_pattern = re.compile(r"\[(\d+):(\d+\.\d+)\](.*)")

        self.has_timestamps = any(timestamp_pattern.match(line) for line in lines)

        if self.has_timestamps:
            self.selection_model = Gtk.SingleSelection.new(self.list_store)
            self.handler_id = self.selection_model.connect(
                "selection-changed", self._on_selection_changed
            )
            self.selection_model.set_selected(0)
        else:
            self.selection_model = Gtk.NoSelection.new(self.list_store)
            self.handler_id = None

        self.list_view.set_model(self.selection_model)

        if self.has_timestamps:
            for line in lines:
                match = timestamp_pattern.match(line)
                if match:
                    minutes = int(match.group(1))
                    seconds = float(match.group(2))
                    text = match.group(3).strip()
                    time_ms = int((minutes * 60 + seconds) * 1000)
                    self.list_store.append(HTLine(text, time_ms))
        else:
            for line in lines:
                text = line.strip()
                if text:
                    self.list_store.append(HTLine(text))

    def clear(self):
        """Clears the lyrics"""
        self.stack.set_visible_child_name("status_page")
        self.list_store.remove_all()

        # Reset selection model
        self.selection_model = None
        self.handler_id = None
        self.has_timestamps = False

    def set_time(self, time_seconds: float):
        """Updates the time of the widget to highlight the correct line

        Args:
            time_seconds (float): the time"""
        if self.list_store.get_n_items() == 0 or not self.has_timestamps:
            return

        time_ms = time_seconds * 1000

        lines = self.list_store.get_n_items()

        new_index = 0
        for i in range(lines):
            line = self.list_store.get_item(i)
            if line.time <= time_ms:
                new_index = i
            else:
                break
        if self.get_mapped():
            if new_index == 0:
                target_position = 0
            else:
                view_height = self.adjustment.get_page_size()
                max_height = self.adjustment.get_upper()
                row_height = max_height / lines
                position = new_index * row_height
                target_position = position - (view_height / 2) + row_height

                target_position = max(0, min(target_position, max_height - view_height))

            if self.autoscroll_enabled:
                self.scroll_error_count = 0
                self._scroll_to(target_position)

        if self.has_timestamps and self.handler_id:
            self.selection_model.handler_block(self.handler_id)
            self.selection_model.select_item(new_index, True)
            self.selection_model.handler_unblock(self.handler_id)

    def _scroll_to(self, value):
        self.animation_is_playing = True
        target = Adw.PropertyAnimationTarget.new(self.adjustment, "value")
        self.scroll_animation = Adw.TimedAnimation.new(
            self, self.adjustment.get_value(), value, 200, target
        )
        self.scrolled_window = self.list_view.get_ancestor(Gtk.ScrolledWindow)
        self.scrolled_window.set_kinetic_scrolling(False)
        self.scroll_animation.play()
        self.scrolled_window.set_kinetic_scrolling(True)

        self.prev_value = value

    def _on_sync_button_click(self, clicked):
        if clicked:
            self.autoscroll_enabled = True
            self.scroll_error_count = 0
            self.sync_button.set_visible(False)

    def _on_scroll(self, scrolling):
        if self.animation_is_playing:
            if self.scroll_animation.get_state() == 3:
                self.animation_is_playing = False
        elif self.scroll_error_count > 1: 
            self.autoscroll_enabled = False
            self.sync_button.set_visible(True)
        else:
            self.scroll_error_count += 1

    
    def _on_selection_changed(self, selection_model, position, n_items):
        if not self.has_timestamps:
            return

        selected_index = selection_model.get_selected()
        if selected_index < self.list_store.get_n_items():
            selected_line = self.list_store.get_item(selected_index)
            if selected_line and selected_line.time > 0:
                self.emit("seek", selected_line.time)

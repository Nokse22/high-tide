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

from gi.repository import Gtk, GObject, Gio, Adw

from ..disconnectable_iface import IDisconnectable

import re


class HTLine(GObject.Object):
    def __init__(self, text="", time=0):
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
            xalign=0.5,
            halign=Gtk.Align.FILL,
            hexpand=True,
            valign=Gtk.Align.FILL,
            vexpand=True,
            wrap=True,
            justify=2,
            margin_start=12,
            margin_top=3,
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

    list_view = Gtk.Template.Child()
    stack = Gtk.Template.Child()

    __gsignals__ = {"seek": (GObject.SignalFlags.RUN_FIRST, None, (int,))}

    def __init__(self, _item=None):
        IDisconnectable.__init__(self)
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        self.list_store = Gio.ListStore.new(HTLine)
        self.factory = LineItemFactory()
        self.selection_model = Gtk.SingleSelection.new(self.list_store)

        self.list_view.set_factory(self.factory)
        self.list_view.set_model(self.selection_model)

        self.adjustment = self.list_view.get_vadjustment()

        self.prev_index = 0
        self.prev_value = 0

        self.handler_id = self.selection_model.connect(
            "selection-changed", self._on_selection_changed
        )

    def set_lyrics(self, lyrics_text : str):
        """Set the lyrics

        Args:
            lyrics_text (str): the lyrics"""
        self.stack.set_visible_child_name("lyrics_page")
        self.list_store.remove_all()

        lines = lyrics_text.splitlines()
        for line in lines:
            match = re.match(r"\[(\d+):(\d+\.\d+)\](.*)", line)
            if match:
                minutes = int(match.group(1))
                seconds = float(match.group(2))
                text = match.group(3).strip()

                time_ms = int((minutes * 60 + seconds) * 1000)

                self.list_store.append(HTLine(text, time_ms))
            else:
                self.list_store.append(HTLine("", 0))

    def clear(self):
        """Clears the lyrics"""
        self.stack.set_visible_child_name("status_page")
        self.list_store.remove_all()

    def set_time(self, time_seconds : float):
        """Updates the time of the widget to highlight the correct line

        Args:
            time_seconds (float): the time"""
        if self.list_store.get_n_items() == 0:
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
            if self.prev_index == new_index:
                target_position = self.prev_value
            elif new_index == 0:
                target_position = 0
            else:
                view_height = self.adjustment.get_page_size()
                max_height = self.adjustment.get_upper()
                row_height = max_height / lines
                position = new_index * row_height
                target_position = position - (view_height / 2) + row_height

                target_position = max(0, min(target_position, max_height - view_height))

            self._scroll_to(target_position)

        self.selection_model.handler_block(self.handler_id)
        self.selection_model.select_item(new_index, True)
        self.selection_model.handler_unblock(self.handler_id)

    def _scroll_to(self, value):
        target = Adw.PropertyAnimationTarget.new(self.adjustment, "value")
        animation = Adw.TimedAnimation.new(
            self, self.adjustment.get_value(), value, 200, target
        )
        animation.play()

        self.prev_value = value

    def _on_selection_changed(self, selection_model, position, n_items):
        selected_index = selection_model.get_selected()
        if selected_index < self.list_store.get_n_items():
            selected_line = self.list_store.get_item(selected_index)
            if selected_line and selected_line.time > 0:
                self.emit("seek", selected_line.time)

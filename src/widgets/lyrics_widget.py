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

from gi.repository import Gtk, GObject, Gio

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
            xalign=0.0,
            halign=Gtk.Align.CENTER,
            hexpand=True,
            wrap=True,
            justify=2)

        list_item.set_child(label)

    def _on_bind(self, factory, list_item):
        label = list_item.get_child()
        lyric_line = list_item.get_item()

        if lyric_line.text:
            label.set_text(lyric_line.text)
        else:
            label.set_text("...")


@Gtk.Template(
    resource_path='/io/github/nokse22/HighTide/ui/widgets/lyrics_widget.ui')
class HTLyricsWidget(Gtk.Box, IDisconnectable):
    __gtype_name__ = 'HTLyricsWidget'

    list_view = Gtk.Template.Child()

    __gsignals__ = {
        'seek': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self, _item=None):
        IDisconnectable.__init__(self)
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        self.list_store = Gio.ListStore.new(HTLine)
        self.factory = LineItemFactory()
        self.selection_model = Gtk.SingleSelection.new(self.list_store)

        # Setup list view
        self.list_view.set_factory(self.factory)
        self.list_view.set_model(self.selection_model)

        self.handler_id = self.selection_model.connect(
            "selection-changed", self._on_selection_changed)

    def set_lyrics(self, lyrics_text):
        self.list_store.remove_all()

        lines = lyrics_text.splitlines()
        for line in lines:
            match = re.match(r'\[(\d+):(\d+\.\d+)\](.*)', line)
            if match:
                minutes = int(match.group(1))
                seconds = float(match.group(2))
                text = match.group(3).strip()

                time_ms = int((minutes * 60 + seconds) * 1000)

                self.list_store.append(HTLine(text, time_ms))
            else:
                self.list_store.append(HTLine("", 0))

    def clear(self):
        self.list_store.remove_all()

    def set_current_line(self, time_seconds):
        if self.list_store.get_n_items() == 0:
            return

        time_ms = time_seconds * 1000

        current_index = 0
        for i in range(self.list_store.get_n_items()):
            line = self.list_store.get_item(i)
            if line.time <= time_ms:
                current_index = i
            else:
                break

        self.selection_model.handler_block(self.handler_id)

        self.list_view.scroll_to(
            current_index, Gtk.ListScrollFlags.SELECT, None)

        self.selection_model.handler_unblock(self.handler_id)

    def _on_selection_changed(self, selection_model, position, n_items):
        selected_index = selection_model.get_selected()
        if selected_index < self.list_store.get_n_items():
            selected_line = self.list_store.get_item(selected_index)
            if selected_line and selected_line.time > 0:
                self.emit("seek", selected_line.time)

# single_type_page.py
#
# Copyright 2023 Nokse
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

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import Gdk

import tidalapi
from tidalapi.page import PageItem, PageLink
from tidalapi.mix import Mix, MixType
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist
from tidalapi.user import Favorites

from ..lib import utils

import threading
import requests
import random

from .page import Page
from ..widgets import CardWidget

class fromFunctionPage(Page):
    __gtype_name__ = 'fromFunctionPage'

    """Used to display lists of albums/artists/mixes/playlists and tracks from a request function"""

    def __init__(self, _window, _type):
        super().__init__(_window)

        self.function = None
        self.type = _type

        self.set_title("More")

        self.parent = None

        self.items = []

        self.items_limit = 50
        self.items_n = 0

    def set_function(self, function):
        self.function = function

        self.scrolled_window.connect("edge-overshot", self.on_edge_overshot)

    def set_items(self, items):
        self.items = items
        print(len(items))

    def on_edge_overshot(self, scrolled_window, pos):
        if pos == Gtk.PositionType.BOTTOM:
            th = threading.Thread(target=self.load_items)
            th.deamon = True
            th.start()

    def _load_page(self):
        self.load_items()

        self._page_loaded()

    def load_items(self):
        print(f"loading {self.items_n} of type {self.type}")

        if self.type == "track":
            self.add_tracks()
        else:
            self.add_cards()

    def add_tracks(self):
        if self.parent == None:
            self.parent = Gtk.ListBox(css_classes=["boxed-list"], margin_bottom=12, margin_start=12, margin_end=12, margin_top=12)
            GLib.idle_add(self.page_content.append,self.parent)

        new_items = []
        if self.function:
            new_items = self.function(limit=self.items_limit, offset=(self.items_n))
            self.items.extend(new_items)
        else:
            new_items = self.items
        self.items_n += self.items_limit
        self.parent.connect("row-activated", self.on_tracks_row_selected)

        for index, track in enumerate(new_items):
            listing = self.get_track_listing(track)
            listing.set_name(str(index))
            self.parent.append(listing)

    def add_cards(self):
        if self.parent == None:
            self.parent = Gtk.FlowBox(selection_mode=0)
            self.page_content.append(self.parent)

        new_items = []
        if self.function:
            new_items = self.function(limit=self.items_limit, offset=(self.items_n))
            self.items.extend(new_items)
        else:
            new_items = self.items
        self.items_n += self.items_limit

        for index, item in enumerate(new_items):
            card = CardWidget(item, self.window)
            GLib.idle_add(self.parent.append, card)

    def on_tracks_row_selected(self, list_box, row):
        index = int(row.get_name())

        self.window.player_object.play_this(self.items, index)

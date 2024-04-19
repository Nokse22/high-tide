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

class fromFunctionPage(Page):
    __gtype_name__ = 'fromFunctionPage'

    """Used to display lists of albums/artists/mixes/playlists and tracks from a request function"""

    def __init__(self, _window, _function, _type):
        super().__init__(_window, _function, _type)

        self.type = _type
        self.function = _function

        self.parent = None

        self.items_limit = 50
        self.items_n = 0

        self.scrolled_window.connect("edge-overshot", self.on_edge_overshot)

    def on_edge_overshot(self, scrolled_window, pos):
        if pos == Gtk.PositionType.BOTTOM:
            th = threading.Thread(target=self.load_items)
            th.deamon = True
            th.start()
            print("reached bottom")

    def _load_page(self):
        self.load_items()

        self._page_loaded()

    def load_items(self):
        print(f"loading {self.items_n} more {self.type}")
        if self.type == "track":
            self.add_tracks()
        elif self.type == "mix":
            self.add_mixes()
        elif self.type == "album":
            self.add_albums()
        elif self.type == "artist":
            self.add_artists()
        elif self.type == "playlist":
            self.add_playlists()

    def add_tracks(self):
        if self.parent == None:
            self.parent = Gtk.ListBox(css_classes=["boxed-list"], margin_bottom=12, margin_start=12, margin_end=12, margin_top=12)
            self.page_content.append(self.parent)

        tracks = self.function(limit=self.items_limit, offset=(self.items_n))
        self.items_n += self.items_limit
        # self.parent.connect("row-activated", self.on_tracks_row_selected, favourite_tracks)

        for index, track in enumerate(tracks):
            listing = self.get_track_listing(track)
            listing.set_name(str(index))
            self.parent.append(listing)

            print("adding track")

    def add_mixes(self):
        if self.parent == None:
            self.parent = Gtk.FlowBox(selection_mode=0)
            self.page_content.append(self.parent)

        mixes = self.function(limit=self.items_limit, offset=(self.items_n))
        self.items_n += self.items_limit

        for index, mix in enumerate(mixes):
            card = self.get_mix_card(mix)
            self.parent.append(card)

            print("adding mix")

    def add_artists(self):
        if self.parent == None:
            self.parent = Gtk.FlowBox(selection_mode=0)
            self.page_content.append(self.parent)

        artists = self.function(limit=self.items_limit, offset=(self.items_n))
        self.items_n += self.items_limit

        for index, artist in enumerate(artists):
            card = self.get_artist_card(artist)
            self.parent.append(card)

            print("adding artist")

    def add_playlists(self):
        if self.parent == None:
            self.parent = Gtk.FlowBox(selection_mode=0)
            self.page_content.append(self.parent)

        playlists = self.function(limit=self.items_limit, offset=(self.items_n))
        self.items_n += self.items_limit

        for index, playlist in enumerate(playlists):
            card = self.get_playlist_card(playlist)
            self.parent.append(card)

            print("adding playlist")

    def add_albums(self):
        if self.parent == None:
            self.parent = Gtk.FlowBox(selection_mode=0)
            self.page_content.append(self.parent)

        albums = self.function(limit=self.items_limit, offset=(self.items_n))
        self.items_n += self.items_limit

        for index, album in enumerate(albums):
            card = self.get_album_card(album)
            self.parent.append(card)

            print("adding album")

    def on_tracks_row_selected(self, list_box, row, favourite_tracks):
        index = int(row.get_name())

        self.window.player_object.current_mix_album_list = favourite_tracks
        track = favourite_tracks[index]
        print(track)
        self.window.player_object.song_album = track.album
        self.window.player_object.play_track(track)
        self.window.player_object.current_song_index = index

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

from ..lib import variables

class singleTypePage(Page):
    __gtype_name__ = 'singleTypePage'

    """Used to display favorites albums/artists/mixes/playlists and tracks"""

    # TODO load only a fixed number of items at first then if the page is scrolled down load some more

    def _load_page(self):
        if self.item == "track":
            self.add_tracks()
        elif self.item == "mix":
            self.add_mixes()
        elif self.item == "album":
            self.add_albums()
        elif self.item == "artist":
            self.add_artists()
        elif self.item == "playlist":
            self.add_playlists()

        self._page_loaded()

    def add_tracks(self):
        tracks_list_box = Gtk.ListBox(css_classes=["boxed-list"], margin_bottom=12, margin_start=12, margin_end=12, margin_top=12)
        self.page_content.append(tracks_list_box)

        favourite_tracks = Favorites(variables.session, variables.session.user.id).tracks(50)
        tracks_list_box.connect("row-activated", self.on_tracks_row_selected, favourite_tracks)

        for index, track in enumerate(favourite_tracks):
            listing = self.get_track_listing(track)
            listing.set_name(str(index))
            tracks_list_box.append(listing)

    def add_mixes(self):
        flow_box = Gtk.FlowBox(selection_mode=0)
        self.page_content.append(flow_box)

        favourites = Favorites(variables.session, variables.session.user.id).mix()

        for index, mix in enumerate(favourites):
            card = self.get_mix_card(mix)
            flow_box.append(card)

    def add_artists(self):
        flow_box = Gtk.FlowBox(selection_mode=0)
        self.page_content.append(flow_box)

        favourites = Favorites(variables.session, variables.session.user.id).artists()

        for index, artist in enumerate(favourites):
            card = self.get_artist_card(artist)
            flow_box.append(card)

    def add_playlists(self):
        flow_box = Gtk.FlowBox(selection_mode=0)
        self.page_content.append(flow_box)

        favourites = Favorites(variables.session, variables.session.user.id).playlists()

        for index, playlist in enumerate(favourites):
            card = self.get_playlist_card(playlist)
            flow_box.append(card)

    def add_albums(self):
        flow_box = Gtk.FlowBox(selection_mode=0)
        self.page_content.append(flow_box)

        favourites = Favorites(variables.session, variables.session.user.id).albums()

        for index, album in enumerate(favourites):
            card = self.get_album_card(album)
            flow_box.append(card)

    def on_tracks_row_selected(self, list_box, row, favourite_tracks):
        index = int(row.get_name())

        variables.player_object.current_mix_album_list = favourite_tracks
        track = favourite_tracks[index]
        print(track)
        variables.player_object.song_album = track.album
        variables.player_object.play_track(track)
        variables.player_object.current_song_index = index

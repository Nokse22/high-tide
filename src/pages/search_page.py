# search_page.py
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

from ..lib import utils
from ..widgets.carousel_widget import CarouselWidget

import threading
import requests
import random

from .page import Page

class searchPage(Page):
    __gtype_name__ = 'searchPage'

    """It is used to display the search results"""

    # TODO Add a card for the top result, it needs to change based on the top result type
    # TODO Implement filters
    # TODO Custom search page with filters (no builder with search_filters.ui)

    def _load_page(self):
        # filter_builder = Gtk.Builder.new_from_resource("/io/github/nokse22/HighTide/ui/search_filter.ui")
        # filters_scrolled_window = filter_builder.get_object("filters_scrolled_window")

        # page_content.prepend(filters_scrolled_window)

        query = self.window.search_entry.get_text()

        results = self.window.session.search(query, [Artist, Album, Playlist, Track], 10)

        # print(query, results)

        top_hit = results["top_hit"]
        # self.page_content.append(Gtk.Label(label=top_hit.name))

        # Adds a carousel with artists, albums and playlists if in the search results

        carousel = self.get_carousel("Artists")
        artists = results["artists"]
        if len(artists) > 0:
            self.page_content.append(carousel)
            for artist in artists:
                artist_card = self.get_artist_card(artist)
                carousel.append_card(artist_card)

        carousel = self.get_carousel("Albums")
        albums = results["albums"]
        if len(albums) > 0:
            self.page_content.append(carousel)
            for album in albums:
                album_card = self.get_album_card(album)
                carousel.append_card(album_card)

        carousel = self.get_carousel("Playlists")
        playlists = results["playlists"]
        if len(playlists) > 0:
            self.page_content.append(carousel)
            for playlist in playlists:
                playlist_card = self.get_playlist_card(playlist)
                carousel.append_card(playlist_card)

        scrolled_window = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)

        self._page_loaded()


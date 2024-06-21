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
from ..widgets.top_hit_widget import TopHitWidget

import threading
import requests
import random

from .page import Page

from ..lib import variables

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

        query = variables.search_entry.get_text()

        results = variables.session.search(query, [Artist, Album, Playlist, Track], 10)

        # print(query, results)

        top_hit = results["top_hit"]
        top_hit_widget = TopHitWidget(top_hit)
        self.page_content.append(top_hit_widget)
        # self.page_content.append(Gtk.Label(label=top_hit.name))
        print(top_hit)

        # Adds a carousel with artists, albums and playlists if in the search results

        carousel = CarouselWidget("Artists")
        artists = results["artists"]
        if len(artists) > 0:
            self.page_content.append(carousel)
            carousel.set_items(artists, "artist")

        carousel = CarouselWidget("Albums")
        albums = results["albums"]
        if len(albums) > 0:
            self.page_content.append(carousel)
            carousel.set_items(albums, "album")

        carousel = CarouselWidget("Playlists")
        playlists = results["playlists"]
        if len(playlists) > 0:
            self.page_content.append(carousel)
            carousel.set_items(playlists, "playlist")

        carousel = CarouselWidget("Tracks")
        tracks = results["tracks"]
        if len(tracks) > 0:
            self.page_content.append(carousel)
            carousel.set_items(tracks, "track")

        scrolled_window = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)

        self._page_loaded()


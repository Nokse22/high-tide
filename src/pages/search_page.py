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

from gi.repository import Gtk

from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from ..widgets.carousel_widget import HTCarouselWidget
from ..widgets.top_hit_widget import HTTopHitWidget

from .page import Page

from ..lib import utils

from ..disconnectable_iface import IDisconnectable


class HTSearchPage(Page):
    __gtype_name__ = 'HTSearchPage'

    """It is used to display the search results"""

    def __init__(self, _search):
        IDisconnectable.__init__(self)
        super().__init__()

        self.search = _search

    def _th_load_page(self):
        results = utils.session.search(
            self.search, [Artist, Album, Playlist, Track], 10)

        top_hit = results["top_hit"]
        top_hit_widget = HTTopHitWidget(top_hit)
        self.page_content.append(top_hit_widget)

        # Adds a carousel with artists, albums and playlists

        carousel = self.get_carousel("Artists")
        artists = results["artists"]
        if len(artists) > 0:
            self.page_content.append(carousel)
            carousel.set_items(artists, "artist")

        carousel = self.get_carousel("Albums")
        albums = results["albums"]
        if len(albums) > 0:
            self.page_content.append(carousel)
            carousel.set_items(albums, "album")

        carousel = self.get_carousel("Playlists")
        playlists = results["playlists"]
        if len(playlists) > 0:
            self.page_content.append(carousel)
            carousel.set_items(playlists, "playlist")

        carousel = self.get_carousel("Tracks")
        tracks = results["tracks"]
        if len(tracks) > 0:
            self.page_content.append(carousel)
            carousel.set_items(tracks, "track")

        self._page_loaded()

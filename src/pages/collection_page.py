# collection_page.py
#
# Copyright 2024 Nokse22
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

from tidalapi.artist import Artist
from tidalapi.mix import MixV2
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from .page import Page

from ..lib import variables

from gettext import gettext as _


class HTCollectionPage(Page):
    __gtype_name__ = 'HTCollectionPage'

    """It is used for the collection"""

    def _th_load_page(self):
        self.set_tag("collection")
        self.set_title(_("Collection"))

        variables.get_favourites()

        self.new_carousel_for(
            _("My Mixes and Radios"), variables.favourite_mixes)
        self.new_carousel_for(
            _("Playlists"), variables.playlist_and_favorite_playlists)
        self.new_carousel_for(
            _("Albums"), variables.favourite_albums)
        self.new_carousel_for(
            _("Tracks"), variables.favourite_tracks)
        self.new_carousel_for(
            _("Artists"), variables.favourite_artists)

        self._page_loaded()

    def new_carousel_for(self, carousel_title, carousel_content):
        if len(carousel_content) == 0:
            return

        carousel = self.get_carousel(carousel_title)
        self.page_content.append(carousel)

        if isinstance(carousel_content[0], MixV2):
            carousel.set_items(carousel_content, "mix")
        elif isinstance(carousel_content[0], Album):
            carousel.set_items(carousel_content, "album")
        elif isinstance(carousel_content[0], Artist):
            carousel.set_items(carousel_content, "artist")
        elif isinstance(carousel_content[0], Playlist):
            carousel.set_items(carousel_content, "playlist")
        elif isinstance(carousel_content[0], Track):
            carousel.set_items(carousel_content, "track")

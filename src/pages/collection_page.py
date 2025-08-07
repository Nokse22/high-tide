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

from .page import Page
from ..lib import utils

from gettext import gettext as _


class HTCollectionPage(Page):
    """It is used for the collection"""

    __gtype_name__ = "HTCollectionPage"

    def _load_async(self):
        ...

    def _load_finish(self):
        self.set_tag("collection")
        self.set_title(_("Collection"))

        self.new_carousel_for(_("My Mixes and Radios"), utils.favourite_mixes)
        self.new_carousel_for(_("Playlists"), utils.playlist_and_favorite_playlists)
        self.new_carousel_for(_("Albums"), utils.favourite_albums)
        self.new_carousel_for(_("Tracks"), utils.favourite_tracks)
        self.new_carousel_for(_("Artists"), utils.favourite_artists)

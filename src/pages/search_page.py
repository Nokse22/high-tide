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

from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from ..widgets.top_hit_widget import HTTopHitWidget

from .page import Page

from ..lib import utils

from ..disconnectable_iface import IDisconnectable
from gettext import gettext as _


class HTSearchPage(Page):
    """It is used to display the search results"""

    __gtype_name__ = "HTSearchPage"

    def __init__(self, _search):
        IDisconnectable.__init__(self)
        super().__init__()

        self.search = _search

        self.results = None

    def _load_async(self):
        self.results = utils.session.search(
            self.search, [Artist, Album, Playlist, Track], 10
        )

    def _load_finish(self):
        self.append(HTTopHitWidget(self.results["top_hit"]))

        self.new_carousel_for(_("Artists"), self.results["artists"])
        self.new_carousel_for(_("Albums"), self.results["albums"])
        self.new_carousel_for(_("Playlists"), self.results["playlists"])
        self.new_carousel_for(_("Tracks"), self.results["tracks"])

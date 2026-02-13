# playlist_page.py
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

from gettext import gettext as _
from gi.repository import Gtk

from .track_list_page import TrackListPage
from ..lib import utils


class HTPlaylistPage(TrackListPage):
    """It is used to display a playlist with author,
    number of tracks and duration"""

    __gtype_name__ = "HTPlaylistPage"

    tracks = None
    auto_load = None
    builder = None
    original_tracks = []
    current_sort = 0

    def _load_async(self):
        self.item = utils.get_playlist(self.id)
        self.tracks = self.item.tracks(limit=50)
        self.original_tracks = self.tracks.copy()

    def _load_finish(self):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/tracks_list_template.ui"
        )

        creator_name = "TIDAL"
        if self.item.creator and self.item.creator.name:
            creator_name = self.item.creator.name

        title = self.item.name
        subtitle = _("by {}").format(creator_name)

        self._setup_ui(
            builder,
            title,
            subtitle,
            self.tracks,
            reload_function=self.item.tracks,
        )

# album_page.py
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


class HTAlbumPage(TrackListPage):
    """A page to display an album"""

    def _load_async(self):
        self.item = utils.get_album(self.id)
        self.top_tracks = self.item.tracks(limit=50)
        self.original_tracks = self.top_tracks.copy()

    def _load_finish(self):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/tracks_list_template.ui"
        )
        title = self.item.name
        subtitle = "{} - {}".format(
            self.item.artist.name,
            (
                self.item.release_date.strftime("%d-%m-%Y")
                if self.item.release_date
                else _("Unknown")
            ),
        )
        self._setup_ui(
            builder, title, subtitle, self.top_tracks, reload_function=self.item.tracks
        )

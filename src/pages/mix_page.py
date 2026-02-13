# mix_page.py
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
from gettext import gettext as _

from .track_list_page import TrackListPage
from ..lib import utils


class HTMixPage(TrackListPage):
    """A page to display a mix"""

    id_type = None
    tracks = []

    @classmethod
    def new_from_track(cls, id):
        instance = cls()
        instance.id = id
        instance.id_type = "track"
        return instance

    @classmethod
    def new_from_artist(cls, id):
        instance = cls()
        instance.id = id
        instance.id_type = "artist"
        return instance

    def _load_async(self):
        if self.id_type is None:
            self.item = utils.get_mix(self.id)
        elif self.id_type == "track":
            self.item = utils.get_track(self.id).get_radio_mix()
        elif self.id_type == "artist":
            self.item = utils.get_artist(self.id).get_radio_mix()

        self.tracks = self.item.items()
        self.original_tracks = self.tracks.copy()

    def _load_finish(self):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/tracks_list_template.ui"
        )
        title = self.item.title
        subtitle = self.item.sub_title

        self._setup_ui(
            builder,
            title,
            subtitle,
            self.tracks,
            reload_function=self.item.items,
            hide_share=True,
        )

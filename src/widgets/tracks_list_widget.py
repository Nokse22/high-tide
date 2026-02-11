# carousel.py
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

from typing import Callable, List

from gi.repository import Gtk
from tidalapi.media import Track

from ..disconnectable_iface import IDisconnectable
from ..lib import utils
from .generic_track_widget import HTGenericTrackWidget


@Gtk.Template(
    resource_path="/io/github/nokse22/high-tide/ui/widgets/tracks_list_widget.ui"
)
class HTTracksListWidget(Gtk.Box, IDisconnectable):
    """It is used to display multiple elements side by side
    with navigation arrows"""

    __gtype_name__ = "HTTracksListWidget"

    tracks_list_box = Gtk.Template.Child()
    more_button = Gtk.Template.Child()
    title_label = Gtk.Template.Child()

    def __init__(self, title):
        IDisconnectable.__init__(self)
        super().__init__()

        self.signals.append(
            (
                self.more_button,
                self.more_button.connect("clicked", self._on_more_clicked),
            )
        )

        self.n_pages = 0

        self.title_name: str = title
        self.title_label.set_label(title)

        self.get_function: Callable = None

        self.signals.append(
            (
                self.tracks_list_box,
                self.tracks_list_box.connect(
                    "row-activated", self._on_tracks_row_selected
                ),
            )
        )

        self.tracks: List[Track] = []

    def set_more_function(self, function: Callable) -> None:
        """Set the function to fetch more items

        Args:
            function: the function"""
        self.get_function = function
        self.tracks = self.get_function(10)
        self.more_button.set_visible(True)

        self._add_tracks()

    def set_tracks_list(self, tracks_list: List[Track]) -> None:
        self.tracks = tracks_list

        self._add_tracks()

    def _add_tracks(self):
        for index, track in enumerate(self.tracks):
            listing = HTGenericTrackWidget(track)
            self.disconnectables.append(listing)
            listing.set_name(str(index))
            self.tracks_list_box.append(listing)

    def _on_more_clicked(self, *args) -> None:
        from ..pages import HTFromFunctionPage

        page = HTFromFunctionPage(self.title_name)
        page.set_function(self.get_function)
        page.load()
        utils.navigation_view.push(page)

    def _on_tracks_row_selected(self, list_box, row) -> None:
        index = int(row.get_name())

        utils.player_object.play_this(self.tracks, index)

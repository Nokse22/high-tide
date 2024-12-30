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

from gi.repository import Gtk

from . import HTGenericTrackWidget

from ..lib import variables


@Gtk.Template(
    resource_path='/io/github/nokse22/HighTide/ui/widgets/tracks_list_widget.ui')
class HTTracksListWidget(Gtk.Box):
    __gtype_name__ = 'HTTracksListWidget'

    """It is used to display multiple elements side by side
    with navigation arrows"""

    tracks_list_box = Gtk.Template.Child()
    more_button = Gtk.Template.Child()
    title_label = Gtk.Template.Child()

    def __init__(self, _title):
        super().__init__()

        self.signals = []

        self.signals.append((
            self,
            self.connect("unrealize", self.__on_unrealized)))

        self.signals.append((
            self.more_button,
            self.more_button.connect("clicked", self.on_more_clicked)))

        self.n_pages = 0

        self.title_name = _title
        self.title_label.set_label(_title)

        self.get_function = None

        self.signals.append((
            self.tracks_list_box,
            self.tracks_list_box.connect(
                "row-activated", self.on_tracks_row_selected)))

        self.tracks = []

    def set_function(self, func):
        self.get_function = func
        self.tracks = self.get_function(10)
        self.more_button.set_visible(True)

        self._add_tracks()

    def set_tracks_list(self, tracks_list):
        self.tracks = tracks_list

        self._add_tracks()

    def _add_tracks(self):
        for index, track in enumerate(self.tracks):
            listing = HTGenericTrackWidget(track, False)
            listing.set_name(str(index))
            self.tracks_list_box.append(listing)

    def on_more_clicked(self, *args):
        from ..pages import fromFunctionPage

        page = fromFunctionPage("track", self.title_name)
        page.set_function(self.get_function)
        page.load()
        variables.navigation_view.push(page)

    def on_tracks_row_selected(self, list_box, row):
        index = int(row.get_name())

        variables.player_object.play_this(self.tracks, index)

    def delete_signals(self):
        disconnected_signals = 0
        for obj, signal_id in self.signals:
            disconnected_signals += 1
            obj.disconnect(signal_id)

            self.signals = []
        print(f"disconnected {disconnected_signals} signals from {self}")

    def __repr__(self, *args):
        return "<HTTracksListWidget>"

    def __on_unrealized(self, *args):
        self.delete_signals()

    def __del__(self, *args):
        print(f"DELETING {self}")

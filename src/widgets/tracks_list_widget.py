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

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gio

from ..lib import utils
from . import GenericTrackWidget

from ..lib import variables

@Gtk.Template(resource_path='/io/github/nokse22/HighTide/ui/widgets/tracks_list_widget.ui')
class TracksListWidget(Gtk.Box):
    __gtype_name__ = 'TracksListWidget'

    """It is used to display multiple elements side by side with navigation arrows"""

    tracks_list_box = Gtk.Template.Child()
    more_button = Gtk.Template.Child()
    title_label = Gtk.Template.Child()

    def __init__(self, _title):
        super().__init__()

        self.n_pages = 0

        self.title_label.set_label(_title)

        self.get_function = None

        self.tracks_list_box.connect("row-activated", self.on_tracks_row_selected)

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
            listing = GenericTrackWidget(track, False)
            listing.set_name(str(index))
            self.tracks_list_box.append(listing)

    @Gtk.Template.Callback("on_more_clicked")
    def on_more_clicked(self, *args):
        if not self.window:
            return

        from ..pages import fromFunctionPage

        page = fromFunctionPage("track")
        page.set_function(self.get_function)
        page.load()
        variables.navigation_view.push(page)

    def on_tracks_row_selected(self, list_box, row):
        index = int(row.get_name())

        variables.player_object.play_this(self.tracks, index)

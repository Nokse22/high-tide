# artist_label_widget.py
#
# Copyright 2024 Nokse
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

import html

class ArtistLabelWidget(Gtk.Label):
    __gtype_name__ = 'ArtistLabelWidget'

    """It is used to display multiple artist with a link"""

    def __init__(self):
        super().__init__(self)

        self.xalign = 0.0

    def set_artists(self, artists):
        label = ""

        for index, artist in enumerate(artists):
            if index >= 1:
                label += ", "
            label += f"""<a href="{artist.id}">{html.escape(artist.name)}</a>"""

            self.set_markup(label)

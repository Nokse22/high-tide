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

from tidalapi import Artist

import html


class HTLinkLabelWidget(Gtk.Label):
    __gtype_name__ = 'HTLinkLabelWidget'

    """It is used to display multiple artist with a link"""

    def __init__(self):
        super().__init__(self)

        self.xalign = 0.0
        self.add_css_class("artist-link")

    def set_artists(self, artists):
        if not isinstance(artists, list) or not isinstance(artists[0], Artist):
            return

        label = ""

        for index, artist in enumerate(artists):
            if index >= 1:
                label += ", "
            label += "<a href='artist:{}'>{}</a>".format(
                artist.id, html.escape(artist.name))

            self.set_markup(label)

    def set_album(self, album):
        label = f"""<a href="album:{album.id}">{html.escape(album.name)}</a>"""
        self.set_markup(label)

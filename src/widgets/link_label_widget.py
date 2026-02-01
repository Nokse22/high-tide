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

import html
from typing import List

from gi.repository import Gtk

from tidalapi.album import Album
from tidalapi.artist import Artist


class HTLinkLabelWidget(Gtk.Label):
    """It is used to display multiple artist with a link"""

    __gtype_name__ = "HTLinkLabelWidget"

    def __init__(self) -> None:
        super().__init__(self)

        self.xalign = 0.0
        self.add_css_class("artist-link")

    def set_artists(self, artists: List[Artist]) -> None:
        """Set the artists for HTLinkLabelWidget

        Args:
            artists: a list of Artists"""
        if not isinstance(artists, list) or not isinstance(artists[0], Artist):
            return

        label: str = ""

        for index, artist in enumerate(artists):
            if index >= 1:
                label += ", "
            label += "<a href='artist:{}'>{}</a>".format(
                artist.id, html.escape(artist.name)
            )

            self.set_markup(label)

    def set_album(self, album: Album) -> None:
        """Set the album for HTLinkLabelWidget

        Args:
            album: an Album"""
        label: str = f"""<a href="album:{album.id}">{html.escape(album.name)}</a>"""
        self.set_markup(label)

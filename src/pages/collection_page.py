# collection_page.py
#
# Copyright 2024 Nokse22
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

from ..lib import utils
from ..widgets import HTCarouselWidget
from .page import Page


class HTCollectionPage(Page):
    """A page to display the collection (the user's library)"""

    __gtype_name__ = "HTCollectionPage"

    def _load_async(self) -> None: ...

    def _load_finish(self) -> None:
        self.set_tag("collection")
        self.set_title(_("Collection"))

        self.new_carousel_for(_("My Mixes and Radios"), utils.favourite_mixes)

        self.playlists_carousel = HTCarouselWidget(_("Playlists"))
        self.playlists_carousel.set_items(utils.playlist_and_favorite_playlists)
        new_playlist_button = Gtk.Button(
            icon_name="list-add-symbolic",
            tooltip_text=_("New Playlist"),
            valign=Gtk.Align.CENTER,
            margin_start=6,
            css_classes=["circular"],
        )
        self.signals.append(
            (
                new_playlist_button,
                new_playlist_button.connect("clicked", lambda *_: utils.new_playlist()),
            )
        )
        self.playlists_carousel.add_header_button(new_playlist_button)
        self.append(self.playlists_carousel)

        self.new_carousel_for(_("Albums"), utils.favourite_albums)
        self.new_carousel_for(_("Tracks"), utils.favourite_tracks)
        self.new_carousel_for(_("Artists"), utils.favourite_artists)

    def update_playlists(self) -> None:
        """Show the playlists again after they changed"""
        self.playlists_carousel.set_items(utils.playlist_and_favorite_playlists)

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

from gi.repository import Adw, Gtk

from tidalapi.types import AlbumOrder, ArtistOrder, ItemOrder, OrderDirection

from ..lib import utils
from ..widgets import HTCarouselWidget
from .activity_page import HTActivityPage
from .page import Page


class HTCollectionPage(Page):
    """A page to display the collection (the user's library)"""

    __gtype_name__ = "HTCollectionPage"

    def _load_async(self) -> None: ...

    @staticmethod
    def _create_paginated_loader(fetch_page, items_cache=None, **fetch_options):
        def load_page(limit: int = 50, offset: int = 0):
            page_items = fetch_page(
                limit=limit, offset=offset, **fetch_options
            )
            if items_cache is not None:
                known_item_ids = {
                    getattr(item, "id", None) for item in items_cache
                }
                items_cache.extend(
                    item
                    for item in page_items
                    if getattr(item, "id", None) not in known_item_ids
                )
            return page_items

        return load_page

    def _load_finish(self) -> None:
        self.set_tag("collection")
        self.set_title(_("Collection"))

        activity_list = Gtk.ListBox(
            css_classes=["boxed-list"],
            selection_mode=Gtk.SelectionMode.NONE,
            margin_start=12,
            margin_end=12,
            margin_top=12,
        )
        activity_row = Adw.ActionRow(
            title=_("My Activity"),
            subtitle=_("Your most played artists of each month"),
            activatable=True,
        )
        activity_row.add_prefix(Gtk.Image(icon_name="music-artist-symbolic"))
        activity_row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        activity_list.append(activity_row)
        self.signals.append(
            (
                activity_row,
                activity_row.connect(
                    "activated",
                    lambda *_: utils.navigation_view.push(HTActivityPage().load()),
                ),
            )
        )
        self.append(activity_list)

        user = utils.session.user
        desc = OrderDirection.Descending

        self.new_carousel_for(
            _("My Mixes and Radios"),
            utils.favourite_mixes,
            self._create_paginated_loader(user.favorites.mixes, utils.favourite_mixes),
        )

        self.playlists_carousel = HTCarouselWidget(_("Playlists"))
        self.playlists_carousel.set_items(utils.playlist_and_favorite_playlists)
        self.playlists_carousel.set_more_function(
            self._create_paginated_loader(
                user.playlist_and_favorite_playlists,
                utils.playlist_and_favorite_playlists,
            )
        )
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

        carousels = [
            (
                _("Albums"),
                utils.favourite_albums,
                user.favorites.albums,
                {"order": AlbumOrder.DateAdded, "order_direction": desc},
            ),
            (
                _("Tracks"),
                utils.favourite_tracks,
                user.favorites.tracks,
                {"order": ItemOrder.Date, "order_direction": desc},
            ),
            (
                _("Artists"),
                utils.favourite_artists,
                user.favorites.artists,
                {"order": ArtistOrder.DateAdded, "order_direction": desc},
            ),
        ]

        for title, items_cache, fetch_page, fetch_options in carousels:
            self.new_carousel_for(
                title,
                items_cache,
                self._create_paginated_loader(
                    fetch_page, items_cache, **fetch_options
                ),
            )

    def update_playlists(self) -> None:
        """Show the playlists again after they changed"""
        self.playlists_carousel.set_items(utils.playlist_and_favorite_playlists)

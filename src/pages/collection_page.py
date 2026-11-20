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
from tidalapi.media import Video
from tidalapi.types import ItemOrder, OrderDirection

from ..lib import utils
from ..widgets import HTCarouselWidget
from .activity_page import HTActivityPage
from .page import Page


class HTCollectionPage(Page):
    """A page to display the collection (the user's library)"""

    __gtype_name__ = "HTCollectionPage"

    waits_for_favourites = True

    def _load_async(self) -> None: ...

    @staticmethod
    def _create_paginated_loader(fetch_page, get_items_cache=None, **fetch_options):
        def load_page(limit: int = 50, offset: int = 0):
            page_items = fetch_page(limit=limit, offset=offset, **fetch_options)
            if get_items_cache is not None:
                items_cache = get_items_cache()
                known_item_ids = {getattr(item, "id", None) for item in items_cache}
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
        # Each carousel with how to get its items, so update_items() can show
        # the collection again after it changed
        self._carousels = []

        self._add_carousel(
            _("My Mixes and Radios"),
            lambda: utils.favourite_mixes,
            self._create_paginated_loader(
                user.favorites.mixes, lambda: utils.favourite_mixes
            ),
        )

        self.playlists_carousel = self._add_carousel(
            _("Playlists"),
            lambda: utils.playlist_and_favorite_playlists,
            self._create_paginated_loader(
                user.playlist_and_favorite_playlists,
                lambda: utils.playlist_and_favorite_playlists,
            ),
            always_shown=True,
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

        self._add_carousel(
            _("Albums"),
            lambda: utils.favourite_albums,
            self._create_paginated_loader(
                user.favorites.albums, lambda: utils.favourite_albums
            ),
        )
        self._add_carousel(
            _("Tracks"),
            lambda: utils.favourite_tracks,
            self._create_paginated_loader(
                user.favorites.tracks,
                lambda: utils.favourite_tracks,
                order=ItemOrder.Date,
                order_direction=OrderDirection.Descending,
            ),
        )
        self._add_carousel(
            _("Artists"),
            lambda: utils.favourite_artists,
            self._create_paginated_loader(
                user.favorites.artists, lambda: utils.favourite_artists
            ),
        )

        self.update_items()

    def _add_carousel(self, title, get_items, more_function, always_shown=False):
        carousel = HTCarouselWidget(title)
        carousel.set_more_function(more_function)
        self._carousels.append((carousel, get_items, always_shown))
        self.append(carousel)
        return carousel

    def update_items(self) -> None:
        """Show the collection again after it changed. Carousels whose items
        didn't change are left as they are, so they keep their scroll position."""
        if not hasattr(self, "_carousels"):
            return  # not loaded yet, it shows the new items when it loads

        def ids(items):
            return [getattr(item, "id", None) for item in items]

        for carousel, get_items, always_shown in self._carousels:
            items = utils.filter_ai_items(get_items())
            shown = len(items) > 0 and not all(
                isinstance(item, Video) for item in items
            )
            carousel.set_visible(always_shown or shown)
            if ids(items) != ids(carousel.items):
                carousel.set_items(items)

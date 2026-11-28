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

from gi.repository import Adw, Gio, Gtk
from tidalapi.media import Video

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
    def _create_paginated_loader(fetch_page, get_items_cache=None, sort_kind=None):
        if sort_kind is not None:
            fetch_page = utils.sorted_fetch(sort_kind, fetch_page)

        def load_page(limit: int = 50, offset: int = 0):
            page_items = fetch_page(limit=limit, offset=offset)
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

        mixes_carousel = self._add_carousel(
            _("My Mixes and Radios"),
            lambda: utils.favourite_mixes,
            self._create_paginated_loader(
                user.favorites.mixes, lambda: utils.favourite_mixes, "mixes"
            ),
        )

        mixes_carousel.more_sort = "mixes"
        mixes_carousel.more_search = (_("Filter by name"), 50)
        self.playlists_carousel = self._add_carousel(
            _("Playlists"),
            lambda: utils.playlist_and_favorite_playlists,
            # All of them are loaded, in the chosen order
            lambda limit=50, offset=0: utils.playlist_and_favorite_playlists[
                offset : offset + limit
            ],
            always_shown=True,
        )
        self._add_playlists_menu()
        # TIDAL gives at most 50 mixes or playlists at a time, other lists 1000
        self.playlists_carousel.more_sort = "playlists"
        self.playlists_carousel.more_search = (_("Filter by name"), 50)

        albums_carousel = self._add_carousel(
            _("Albums"),
            lambda: utils.favourite_albums,
            self._create_paginated_loader(
                user.favorites.albums, lambda: utils.favourite_albums, "albums"
            ),
        )
        albums_carousel.more_sort = "albums"
        albums_carousel.more_search = (_("Filter by title or artist"), 1000)
        tracks_carousel = self._add_carousel(
            _("Tracks"),
            lambda: utils.favourite_tracks,
            self._create_paginated_loader(
                user.favorites.tracks, lambda: utils.favourite_tracks, "tracks"
            ),
        )
        tracks_carousel.more_source = utils.MY_TRACKS
        self._add_tracks_menu(tracks_carousel)
        tracks_carousel.more_sort = "tracks"
        tracks_carousel.more_search = (_("Filter by title, artist or album"), 1000)
        artists_carousel = self._add_carousel(
            _("Artists"),
            lambda: utils.favourite_artists,
            self._create_paginated_loader(
                user.favorites.artists, lambda: utils.favourite_artists, "artists"
            ),
        )

        artists_carousel.more_sort = "artists"
        artists_carousel.more_search = (_("Filter by name"), 1000)

        self.update_items()

    def _add_playlists_menu(self) -> None:
        """Add the Playlists row's menu: a new playlist, and how they're sorted"""
        sort_menu, actions = utils.sort_menu("playlists")
        new_actions = Gio.SimpleActionGroup()
        new_action = Gio.SimpleAction.new("new-playlist", None)
        self.signals.append(
            (new_action, new_action.connect("activate", lambda *_: utils.new_playlist()))
        )
        new_actions.add_action(new_action)
        folder_action = Gio.SimpleAction.new("new-folder", None)
        self.signals.append(
            (folder_action, folder_action.connect("activate", lambda *_: utils.new_folder()))
        )
        new_actions.add_action(folder_action)

        menu = Gio.Menu()
        menu.append(_("New playlist…"), "collection.new-playlist")
        menu.append(_("New folder…"), "collection.new-folder")
        menu.append_submenu(_("Sort by"), sort_menu)

        button = Gtk.MenuButton(
            icon_name="view-more-symbolic",
            tooltip_text=_("Playlist Options"),
            valign=Gtk.Align.CENTER,
            margin_start=6,
            css_classes=["circular"],
        )
        # On the button itself: the row was added before, and GTK then keeps
        # looking past an ancestor that gets actions later (items show greyed out)
        button.insert_action_group("collection", new_actions)
        button.insert_action_group("sort", actions)
        self.playlists_carousel.add_header_button(button)
        button.set_menu_model(menu)
        button.get_popover().set_flags(Gtk.PopoverMenuFlags.NESTED)

    def _add_tracks_menu(self, carousel) -> None:
        """Play all saved songs from the Tracks row without opening the list first
        (#142): a split button, Play on its main part and Shuffle and the queue
        options under its arrow"""
        actions = Gio.SimpleActionGroup()

        def saved_tracks():
            return [
                t
                for t in utils.filter_ai_items(list(utils.favourite_tracks))
                if not utils.is_hidden_by_block(t)
            ]

        def play(shuffle):
            tracks = saved_tracks()
            if not tracks:
                return
            if shuffle:
                utils.player_object.shuffle_this(tracks, source=utils.MY_TRACKS)
            else:
                utils.player_object.play_this(tracks, 0, source=utils.MY_TRACKS)

        shuffle_action = Gio.SimpleAction.new("shuffle", None)
        self.signals.append(
            (shuffle_action, shuffle_action.connect("activate", lambda *_: play(True)))
        )
        actions.add_action(shuffle_action)

        menu = Gio.Menu()
        shuffle_section = Gio.Menu()
        shuffle_section.append(_("Shuffle"), "my-tracks.shuffle")
        menu.append_section(None, shuffle_section)
        queue, queue_actions = utils.queue_menu(utils.MY_TRACKS)
        menu.append_section(None, queue)

        button = Adw.SplitButton(
            child=Adw.ButtonContent(
                icon_name="media-playback-start-symbolic", label=_("Play")
            ),
            menu_model=menu,
            tooltip_text=_("Play My Tracks"),
            dropdown_tooltip=_("My Tracks Options"),
            valign=Gtk.Align.CENTER,
            margin_start=6,
        )
        self.signals.append((button, button.connect("clicked", lambda *_: play(False))))
        # On the button itself, as for the Playlists row
        button.insert_action_group("my-tracks", actions)
        button.insert_action_group("queue", queue_actions)
        carousel.add_header_button(button)

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

        def shown_as(items):
            # What the cards show, so a renamed playlist or folder, or a folder
            # with more or fewer playlists, is shown again too
            return [
                (
                    getattr(item, "id", None),
                    getattr(item, "name", None),
                    getattr(item, "title", None),
                    getattr(item, "total_number_of_items", None),
                )
                for item in items
            ]

        for carousel, get_items, always_shown in self._carousels:
            items = utils.filter_ai_items(get_items())
            shown = len(items) > 0 and not all(
                isinstance(item, Video) for item in items
            )
            carousel.set_visible(always_shown or shown)
            # Compared with what the cards were made from, not carousel.items:
            # a rename changes the very objects the row holds
            now = shown_as(items)
            if now != getattr(carousel, "shown_as", None):
                carousel.set_items(items)
                carousel.shown_as = now

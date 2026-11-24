# playlist_page.py
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

from gettext import gettext as _

from gi.repository import Gtk

from .track_list_page import TrackListPage
from ..lib import utils
from ..widgets.playlist_options import PlaylistOptions


class HTPlaylistPage(TrackListPage):
    """It is used to display a playlist with author,
    number of tracks and duration"""

    __gtype_name__ = "HTPlaylistPage"

    tracks = None
    auto_load = None
    builder = None
    original_tracks = []
    current_sort = 0

    def _load_async(self):
        self.item = utils.get_playlist(self.id)
        self.tracks = self.item.tracks(limit=50)
        self.original_tracks = self.tracks.copy()

    def _load_finish(self):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/tracks_list_template.ui"
        )

        creator_name = "TIDAL"
        if self.item.creator and self.item.creator.name:
            creator_name = self.item.creator.name

        title = self.item.name
        subtitle = _("by {}").format(creator_name)

        is_own_playlist = utils.is_own_playlist(self.item)
        if is_own_playlist:
            builder.get_object("_auto_load").set_playlist(self.item)

        self._setup_ui(
            builder,
            title,
            subtitle,
            self.tracks,
            reload_function=self.item.tracks,
        )

        # Own and saved playlists: edit, public/private, move to folder, delete
        if PlaylistOptions.applies_to(self.item):
            self._setup_playlist_menu(builder)

    def _setup_playlist_menu(self, builder):
        self.title_label = builder.get_object("_title_label")
        self.options = PlaylistOptions(
            self.item, self._on_playlist_changed, self._on_deleted
        )
        # On the content, not the page: the page's scrolled window doesn't see
        # action groups inserted on the page
        builder.get_object("_main").insert_action_group("playlist", self.options.actions)

        menu_button = builder.get_object("_playlist_menu_button")
        # After Play next and Add to queue
        self.page_menu.append_section(None, self.options.menu)
        # Move to folder opens beside the menu on hover, like the song menu's
        # submenus, instead of replacing it after a click
        menu_button.get_popover().set_flags(Gtk.PopoverMenuFlags.NESTED)
        menu_button.set_visible(True)
        # The folders can change meanwhile: listed when the menu opens
        self.signals.append(
            (
                menu_button,
                menu_button.connect(
                    "notify::active",
                    lambda b, _p: b.get_active() and self.options.update(),
                ),
            )
        )

    def _on_playlist_changed(self, playlist):
        self.item = playlist
        self.set_title(playlist.name)
        self.title_label.set_label(playlist.name)

    def _on_deleted(self):
        if utils.navigation_view.get_visible_page() is self:
            utils.navigation_view.pop()
        else:
            utils.navigation_view.remove(self)
